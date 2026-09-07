"""Ceselsan Zil Takip Programı - Ana pencere (Tkinter arayüzü)."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import uuid
from datetime import date, datetime, timedelta
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

import app_logging
import audio_player
import autostart
import prayer_service
import remote_control
import ring_history
from config_store import (VAKIT_KEYS, complete_config, load_config,
                           load_paired_devices_raw, save_config, save_paired_devices_raw)
from scheduler import BellScheduler
from single_instance import SingleInstance

try:
    import tray_icon
except Exception:  # pystray/Pillow bulunamazsa tepsi özelliği sessizce devre dışı kalır
    tray_icon = None

APP_TITLE = "Ceselsan Zil Takip Programı"
DAY_NAMES = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
DAY_SHORT = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

ACCENT = "#2f6f4f"
ACCENT_DARK = "#1f4a34"
BG = "#f4f6f5"
ROW_ODD = "#e9efec"
ROW_EVEN = "#ffffff"
FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")

RING_KIND_LABELS = {
    "entry": "Zil Programı",
    "prayer": "Namaz Vakti",
    "friday": "Cuma Namazı",
    "holiday": "Tatil Günü",
    "fire_button": "Yangın Butonu",
    "remote": "Uzaktan Zil",
    "remote_fire_button": "Uzaktan Yangın Butonu",
}


def format_days(days: list[int]) -> str:
    return ", ".join(DAY_SHORT[d] for d in sorted(days)) if days else "-"


def format_sound(sound: Optional[str]) -> str:
    if not sound or sound == "default":
        return "(Ses Ayarları'ndaki varsayılan ses)"
    return sound


def format_holiday_date(iso_date: str) -> str:
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return iso_date


class EntryDialog(tk.Toplevel):
    """Zil programına yeni kayıt ekleme / düzenleme penceresi."""

    def __init__(self, parent, entry: Optional[dict] = None):
        super().__init__(parent)
        self.title("Zil Kaydı")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.result: Optional[dict] = None
        self.transient(parent)
        self.grab_set()

        entry = entry or {}
        self.label_var = tk.StringVar(value=entry.get("label", ""))
        self.time_var = tk.StringVar(value=entry.get("time", "08:00"))
        self.enabled_var = tk.BooleanVar(value=entry.get("enabled", True))
        existing_sound = entry.get("sound")
        self.sound_var = tk.StringVar(
            value="" if not existing_sound or existing_sound == "default" else existing_sound)
        self.day_vars = [tk.BooleanVar(value=(i in entry.get("days", [])))
                          for i in range(7)]

        pad = {"padx": 10, "pady": 6}
        row = 0
        ttk.Label(self, text="Etiket:").grid(row=row, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.label_var, width=32).grid(
            row=row, column=1, columnspan=3, sticky="we", **pad)
        row += 1

        ttk.Label(self, text="Saat (SS:DD):").grid(row=row, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.time_var, width=10).grid(
            row=row, column=1, sticky="w", **pad)
        row += 1

        ttk.Label(self, text="Günler:").grid(row=row, column=0, sticky="nw", **pad)
        days_frame = ttk.Frame(self)
        days_frame.grid(row=row, column=1, columnspan=3, sticky="w", **pad)
        for i, name in enumerate(DAY_NAMES):
            ttk.Checkbutton(days_frame, text=name, variable=self.day_vars[i]).grid(
                row=i // 4, column=i % 4, sticky="w", padx=4, pady=2)
        row += 1

        ttk.Label(self, text="Ses dosyası:").grid(row=row, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.sound_var, width=32).grid(
            row=row, column=1, columnspan=2, sticky="we", **pad)
        ttk.Button(self, text="📁 Seç...", command=self._choose_sound).grid(
            row=row, column=3, sticky="w", **pad)
        row += 1
        ttk.Label(self, text="Boş bırakılırsa Ses Ayarları'ndaki varsayılan ses çalınır.",
                  foreground="#666666").grid(row=row, column=1, columnspan=3, sticky="w", padx=10)
        row += 1

        ttk.Checkbutton(self, text="Etkin", variable=self.enabled_var).grid(
            row=row, column=0, columnspan=2, sticky="w", **pad)
        row += 1

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=row, column=0, columnspan=4, pady=10)
        ttk.Button(btn_frame, text="💾 Kaydet", style="Accent.TButton",
                   command=self._on_save).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="İptal", command=self.destroy).pack(side="left", padx=6)

        self.existing_id = entry.get("id")

    def _choose_sound(self) -> None:
        path = filedialog.askopenfilename(
            title="Ses dosyası seç",
            filetypes=[("Ses dosyaları", "*.wav *.mp3 *.ogg *.flac"), ("Tüm dosyalar", "*.*")])
        if path:
            self.sound_var.set(path)

    def _on_save(self) -> None:
        label = self.label_var.get().strip() or "Zil"
        time_str = self.time_var.get().strip()
        try:
            datetime.strptime(time_str, "%H:%M")
        except ValueError:
            messagebox.showerror(APP_TITLE, "Saat SS:DD formatında olmalıdır. Örnek: 08:30")
            return
        days = [i for i, v in enumerate(self.day_vars) if v.get()]
        if not days:
            messagebox.showerror(APP_TITLE, "En az bir gün seçmelisiniz.")
            return
        self.result = {
            "id": self.existing_id or str(uuid.uuid4()),
            "label": label,
            "time": time_str,
            "days": days,
            "sound": self.sound_var.get().strip() or "default",
            "enabled": self.enabled_var.get(),
        }
        self.destroy()


class FridayOffsetDialog(tk.Toplevel):
    """Cuma namazına göre (öncesi/sonrası) çalınacak zil ekleme/düzenleme
    penceresi - ör. namazdan 15 dk önce paydos zili, namazdan 30 dk sonra
    mesaiye dönüş zili. İstediğiniz kadar bağımsız kayıt eklenebilir."""

    def __init__(self, parent, offset: Optional[dict] = None):
        super().__init__(parent)
        self.title("Cuma Namazı Zil Zamanı")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.result: Optional[dict] = None
        self.transient(parent)
        self.grab_set()

        offset = offset or {}
        self.existing_id = offset.get("id")
        self.minutes_var = tk.IntVar(value=offset.get("minutes", 15))
        self.direction_var = tk.StringVar(value=offset.get("direction", "before"))
        self.label_var = tk.StringVar(value=offset.get("label", ""))
        self.enabled_var = tk.BooleanVar(value=offset.get("enabled", True))
        self.sound_var = tk.StringVar(value=offset.get("sound") or "")

        pad = {"padx": 10, "pady": 6}
        ttk.Label(self, text="Kaç dakika:").grid(row=0, column=0, sticky="w", **pad)
        ttk.Spinbox(self, from_=1, to=180, textvariable=self.minutes_var, width=8).grid(
            row=0, column=1, sticky="w", **pad)

        direction_frame = ttk.Frame(self)
        direction_frame.grid(row=1, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 6))
        ttk.Radiobutton(direction_frame, text="Namazdan Önce (paydos/uyarı zili)",
                         variable=self.direction_var, value="before").pack(
            side="left", padx=(0, 16))
        ttk.Radiobutton(direction_frame, text="Namazdan Sonra (ör. mesaiye dönüş)",
                         variable=self.direction_var, value="after").pack(side="left")

        ttk.Label(self, text="Etiket:").grid(row=2, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.label_var, width=36).grid(
            row=2, column=1, columnspan=2, sticky="we", **pad)

        ttk.Label(self, text="Ses dosyası:").grid(row=3, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.sound_var, width=28).grid(
            row=3, column=1, sticky="we", **pad)
        ttk.Button(self, text="📁 Seç...", command=self._choose_sound).grid(
            row=3, column=2, sticky="w", **pad)
        ttk.Label(self, text="Boş bırakılırsa Ses Ayarları'ndaki varsayılan ses çalınır.",
                  foreground="#666666").grid(row=4, column=0, columnspan=3, sticky="w", padx=10)

        ttk.Checkbutton(self, text="Etkin", variable=self.enabled_var).grid(
            row=5, column=0, columnspan=2, sticky="w", **pad)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=6, column=0, columnspan=3, pady=10)
        ttk.Button(btn_frame, text="💾 Kaydet", style="Accent.TButton",
                   command=self._on_save).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="İptal", command=self.destroy).pack(side="left", padx=6)

    def _choose_sound(self) -> None:
        path = filedialog.askopenfilename(
            title="Ses dosyası seç",
            filetypes=[("Ses dosyaları", "*.wav *.mp3 *.ogg *.flac"), ("Tüm dosyalar", "*.*")])
        if path:
            self.sound_var.set(path)

    def _on_save(self) -> None:
        minutes = self.minutes_var.get()
        direction = self.direction_var.get()
        direction_text = "dk kala" if direction == "before" else "dk sonra"
        label = self.label_var.get().strip() or f"Cuma Namazı - {minutes} {direction_text}"
        self.result = {
            "id": self.existing_id or str(uuid.uuid4()),
            "minutes": minutes,
            "direction": direction,
            "label": label,
            "enabled": self.enabled_var.get(),
            "sound": self.sound_var.get().strip() or None,
        }
        self.destroy()


class HolidayDialog(tk.Toplevel):
    """Tatil günü ekleme/düzenleme penceresi. Varsayılan olarak bu tarihte
    hiçbir zil çalmaz; "Bu tarihte özel bir zil çalsın mı?" işaretlenirse
    normal program/namaz vakitleri yine çalmaz ama seçilen saatte tek
    seferlik özel bir zil çalar."""

    def __init__(self, parent, holiday: Optional[dict] = None):
        super().__init__(parent)
        self.title("Tatil Günü" if holiday is None else "Tatil Gününü Düzenle")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.result: Optional[dict] = None
        self.transient(parent)
        self.grab_set()

        holiday = holiday or {}
        self.existing_date = holiday.get("date")
        self.date_var = tk.StringVar(
            value=format_holiday_date(holiday["date"]) if holiday.get("date")
            else datetime.now().strftime("%d.%m.%Y"))
        self.label_var = tk.StringVar(value=holiday.get("label", ""))
        self.ring_var = tk.BooleanVar(value=bool(holiday.get("ring")))
        self.ring_time_var = tk.StringVar(value=holiday.get("ring_time") or "09:00")
        ring_sound = holiday.get("ring_sound")
        self.ring_sound_var = tk.StringVar(value="" if not ring_sound else ring_sound)

        pad = {"padx": 10, "pady": 6}
        ttk.Label(self, text="Tarih (GG.AA.YYYY):").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.date_var, width=14).grid(
            row=0, column=1, columnspan=2, sticky="w", **pad)

        ttk.Label(self, text="Açıklama:").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.label_var, width=32).grid(
            row=1, column=1, columnspan=2, sticky="we", **pad)

        ttk.Separator(self, orient="horizontal").grid(
            row=2, column=0, columnspan=3, sticky="we", padx=10, pady=(6, 2))

        ttk.Checkbutton(self, text="Bu tarihte özel bir zil çalsın mı?",
                         variable=self.ring_var, command=self._update_ring_state).grid(
            row=3, column=0, columnspan=3, sticky="w", **pad)
        ttk.Label(self, text="İşaretlemezseniz bu tarihte hiç zil çalmaz (klasik tatil günü).\n"
                              "İşaretlerseniz normal program/namaz vakitleri yine çalmaz, ama\n"
                              "aşağıdaki saatte tek seferlik özel bir zil çalar.",
                  foreground="#666666", justify="left").grid(
            row=4, column=0, columnspan=3, sticky="w", padx=10)

        self.ring_time_label = ttk.Label(self, text="Saat (SS:DD):")
        self.ring_time_label.grid(row=5, column=0, sticky="w", **pad)
        self.ring_time_entry = ttk.Entry(self, textvariable=self.ring_time_var, width=10)
        self.ring_time_entry.grid(row=5, column=1, sticky="w", **pad)

        self.ring_sound_label = ttk.Label(self, text="Ses dosyası:")
        self.ring_sound_label.grid(row=6, column=0, sticky="w", **pad)
        self.ring_sound_entry = ttk.Entry(self, textvariable=self.ring_sound_var, width=28)
        self.ring_sound_entry.grid(row=6, column=1, sticky="we", **pad)
        self.ring_sound_button = ttk.Button(self, text="📁 Seç...", command=self._choose_ring_sound)
        self.ring_sound_button.grid(row=6, column=2, sticky="w", **pad)
        self.ring_sound_hint = ttk.Label(
            self, text="Boş bırakılırsa Ses Ayarları'ndaki varsayılan ses çalınır.",
            foreground="#666666")
        self.ring_sound_hint.grid(row=7, column=0, columnspan=3, sticky="w", padx=10)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=8, column=0, columnspan=3, pady=10)
        ttk.Button(btn_frame, text="💾 Kaydet", style="Accent.TButton",
                   command=self._on_save).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="İptal", command=self.destroy).pack(side="left", padx=6)

        self._update_ring_state()

    def _update_ring_state(self) -> None:
        state = "normal" if self.ring_var.get() else "disabled"
        for widget in (self.ring_time_label, self.ring_time_entry, self.ring_sound_label,
                       self.ring_sound_entry, self.ring_sound_button, self.ring_sound_hint):
            widget.configure(state=state)

    def _choose_ring_sound(self) -> None:
        path = filedialog.askopenfilename(
            title="Ses dosyası seç",
            filetypes=[("Ses dosyaları", "*.wav *.mp3 *.ogg *.flac"), ("Tüm dosyalar", "*.*")])
        if path:
            self.ring_sound_var.set(path)

    def _on_save(self) -> None:
        date_str = self.date_var.get().strip()
        try:
            parsed = datetime.strptime(date_str, "%d.%m.%Y")
        except ValueError:
            messagebox.showerror(APP_TITLE, "Tarih GG.AA.YYYY formatında olmalıdır. Örnek: 23.04.2027")
            return
        ring = self.ring_var.get()
        if ring:
            ring_time = self.ring_time_var.get().strip()
            try:
                datetime.strptime(ring_time, "%H:%M")
            except ValueError:
                messagebox.showerror(APP_TITLE, "Saat SS:DD formatında olmalıdır. Örnek: 09:00")
                return
        else:
            ring_time = None
        self.result = {
            "date": parsed.strftime("%Y-%m-%d"),
            "label": self.label_var.get().strip(),
            "ring": ring,
            "ring_time": ring_time if ring else None,
            "ring_sound": (self.ring_sound_var.get().strip() or None) if ring else None,
        }
        self.destroy()


class PairingApprovalDialog(tk.Toplevel):
    """Gelen bir eşleştirme isteği için onay penceresi. messagebox.askyesno
    yerine özel bir Toplevel kullanılıyor çünkü bunun görünür bir geri
    sayımı var ve [TIMEOUT_SECONDS] içinde yanıtlanmazsa otomatik olarak
    "Hayır" ile kapanır - kullanıcı ekranı görmeden uzakta bekleyen bir
    isteği sonsuza kadar askıda bırakmaz."""

    TIMEOUT_SECONDS = 30

    def __init__(self, parent, requester_name: str):
        super().__init__(parent)
        self.title("Eşleştirme İsteği")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.result = False
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_no)

        self._remaining = self.TIMEOUT_SECONDS
        self._timer_id: Optional[str] = None

        ttk.Label(
            self, justify="left", wraplength=360,
            text=f"'{requester_name}' bu cihaza eşleştirme kodu ile bağlanmak "
                 "istiyor.\n\nOnaylıyor musunuz? Onaylarsanız bu cihaz zili "
                 "uzaktan çaldırabilir, durdurabilir ve tüm ayarları "
                 "görüntüleyip değiştirebilir.").pack(padx=20, pady=(20, 10))

        self._countdown_var = tk.StringVar()
        ttk.Label(self, textvariable=self._countdown_var, foreground="#666666").pack(
            pady=(0, 10))
        self._update_countdown_text()

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=(0, 20))
        ttk.Button(btn_frame, text="Hayır", command=self._on_no).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Evet", style="Accent.TButton",
                   command=self._on_yes).pack(side="left", padx=6)

        self._timer_id = self.after(1000, self._tick)

    def _update_countdown_text(self) -> None:
        self._countdown_var.set(
            f"{self._remaining} saniye içinde yanıtlanmazsa otomatik reddedilecek.")

    def _tick(self) -> None:
        self._remaining -= 1
        if self._remaining <= 0:
            self._on_no()
            return
        self._update_countdown_text()
        self._timer_id = self.after(1000, self._tick)

    def _on_yes(self) -> None:
        self.result = True
        self._close()

    def _on_no(self) -> None:
        self.result = False
        self._close()

    def _close(self) -> None:
        if self._timer_id is not None:
            try:
                self.after_cancel(self._timer_id)
            except Exception:
                pass
            self._timer_id = None
        self.destroy()


class ExportCodeDialog(tk.Toplevel):
    """Ayarları dışa aktarmak için bir kod üretip gösteren pencere - tıpkı
    "Uzaktan Erişim" sekmesindeki eşleştirme koduna benziyor, ama kalıcı bir
    ilişki kurmaz: yalnızca kodu bilen İLK cihaza, üretim anındaki ayarların
    TEK SEFERLİK bir kopyasını gönderir."""

    def __init__(self, parent, manager: "remote_control.RemoteControlManager",
                 config: dict) -> None:
        super().__init__(parent)
        self.title("Ayarları Dışa Aktar")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.manager = manager
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        code = manager.generate_export_code(config)

        ttk.Label(
            self, justify="left", wraplength=380,
            text='Bu kodu, ayarları almak istediğiniz cihazda "Kod ile İçe Aktar" ekranına '
                 "girin. Yalnızca aynı yerel ağda (WiFi) çalışır.").pack(
            padx=20, pady=(20, 10))

        code_row = ttk.Frame(self)
        code_row.pack(padx=20, pady=(0, 4))
        self.code_var = tk.StringVar(value=code)
        ttk.Entry(code_row, textvariable=self.code_var, font=("Consolas", 20, "bold"),
                  width=22, justify="left", state="readonly").pack(side="left")
        ttk.Button(code_row, text="📋 Kopyala", command=self._copy_code).pack(
            side="left", padx=(8, 0))

        ttk.Label(self, text="5 dakika içinde girilmezse ya da bir kez kullanılınca bu kod "
                              "geçersiz olur.", foreground="#666666").pack(
            padx=20, pady=(0, 16))

        ttk.Button(self, text="Kapat", command=self._on_close).pack(pady=(0, 16))

    def _copy_code(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.code_var.get())

    def _on_close(self) -> None:
        self.manager.cancel_export_code()
        self.destroy()


class ImportCodeDialog(tk.Toplevel):
    """Bir cihazda gösterilen dışa aktarma kodunu girip o cihazın ayarlarını
    almak için kullanılan pencere. Başarılıysa self.result = (host_name,
    config) olur, aksi halde None kalır (İptal/kapatma/zaman aşımı)."""

    def __init__(self, parent, manager: "remote_control.RemoteControlManager") -> None:
        super().__init__(parent)
        self.title("Kod ile İçe Aktar")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.manager = manager
        self.result: Optional[tuple[str, dict]] = None
        self._busy = False
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        ttk.Label(
            self, justify="left", wraplength=360,
            text='Ayarlarını almak istediğiniz cihazda "Dışa Aktar" ile üretilen kodu buraya '
                 "girin.").pack(padx=20, pady=(20, 10))

        row = ttk.Frame(self)
        row.pack(padx=20, pady=(0, 4))
        self.code_entry_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.code_entry_var, width=24).pack(side="left")
        self.submit_btn = ttk.Button(row, text="İçe Aktar", style="Accent.TButton",
                                      command=self._on_submit)
        self.submit_btn.pack(side="left", padx=(8, 0))

        self.status_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status_var, foreground="#666666",
                  wraplength=360, justify="left").pack(padx=20, pady=(4, 16))

    def _on_submit(self) -> None:
        code = self.code_entry_var.get().strip()
        if not code or self._busy:
            return
        self._busy = True
        self.submit_btn.state(["disabled"])
        self.status_var.set("Aranıyor...")

        def worker() -> None:
            def status(text: str) -> None:
                try:
                    self.after(0, lambda: self.status_var.set(text))
                except RuntimeError:
                    pass
            result = self.manager.request_config_export(code, status)
            try:
                self.after(0, lambda: self._finish(result))
            except RuntimeError:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, result: Optional[tuple[str, dict]]) -> None:
        self._busy = False
        self.submit_btn.state(["!disabled"])
        if result is None:
            return
        self.result = result
        self.destroy()


class ConfigTabsMixin:
    """Zil Programı/Namaz Vakitleri/tatil günleri/varsayılan ses sekmelerini
    kuran ve düzenleyen ortak metodlar. Hem App (yerel ayarlar) hem de
    RemoteSettingsWindow (uzak bir cihazın ayarları) bu metodları aynen
    kullanır - tek fark her sınıfın kendi _persist()/_log()/
    _play_test_sound() metodunu sağlamasıdır (yerelde diske kaydet/yerelde
    çal; uzakta ise "set_config"/"ring_now" komutuyla ağ üzerinden gönder).

    KASITLI OLARAK BURADA DEĞİL: ses çıkış cihazı seçimi (Çıkış cihazı
    listesi HANGİ makinede çalıştırılıyorsa O makinenin hoparlörlerini
    listeler - uzaktan anlamsız/yanıltıcı olurdu), sistem tepsisi, Windows
    açılışında otomatik başlatma, log klasörünü açma - bunların hepsi
    yalnızca ayarı değiştirdiğiniz FİZİKSEL makinede anlamlıdır, bu yüzden
    yalnızca App sınıfında (yerel ayarlarda) kalır.
    """

    # ---------- Ortak: kaydırmalı alan ----------
    def _make_scrollable(self, parent: ttk.Frame) -> ttk.Frame:
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        inner = ttk.Frame(canvas)
        inner_window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event) -> None:
            canvas.itemconfig(inner_window, width=event.width)

        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event) -> None:
            if event.num == 5 or event.delta < 0:
                canvas.yview_scroll(1, "units")
            elif event.num == 4 or event.delta > 0:
                canvas.yview_scroll(-1, "units")

        def _bind_mousewheel(_event=None) -> None:
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
            canvas.bind_all("<Button-4>", _on_mousewheel)
            canvas.bind_all("<Button-5>", _on_mousewheel)

        def _unbind_mousewheel(_event=None) -> None:
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", _bind_mousewheel)
        canvas.bind("<Leave>", _unbind_mousewheel)

        return inner

    # ---------- Zil programı sekmesi ----------
    def _build_entries_tab(self) -> None:
        frame = self.entries_tab
        columns = ("enabled", "label", "time", "days", "sound")
        self.entries_tree = ttk.Treeview(frame, columns=columns, show="headings", height=12)
        headers = {"enabled": "Etkin", "label": "Etiket", "time": "Saat",
                   "days": "Günler", "sound": "Ses"}
        widths = {"enabled": 60, "label": 220, "time": 70, "days": 160, "sound": 220}
        for col in columns:
            self.entries_tree.heading(col, text=headers[col])
            self.entries_tree.column(col, width=widths[col], anchor="w")
        self.entries_tree.tag_configure("oddrow", background=ROW_ODD)
        self.entries_tree.tag_configure("evenrow", background=ROW_EVEN)
        self.entries_tree.pack(fill="both", expand=True, padx=8, pady=8)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btn_frame, text="➕ Ekle", style="Accent.TButton",
                   command=self._add_entry).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="✏️ Düzenle", command=self._edit_entry).pack(
            side="left", padx=4)
        ttk.Button(btn_frame, text="🗑️ Sil", command=self._delete_entry).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="▶ Şimdi Çal (Test)", command=self._test_entry).pack(
            side="left", padx=4)
        self._refresh_entries_tree()

    def _refresh_entries_tree(self) -> None:
        self.entries_tree.delete(*self.entries_tree.get_children())
        for i, entry in enumerate(self.cfg["entries"]):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            self.entries_tree.insert("", "end", iid=entry["id"], tags=(tag,), values=(
                "Evet" if entry.get("enabled", True) else "Hayır",
                entry.get("label", ""),
                entry.get("time", ""),
                format_days(entry.get("days", [])),
                format_sound(entry.get("sound")),
            ))

    def _add_entry(self) -> None:
        dialog = EntryDialog(self)
        self.wait_window(dialog)
        if dialog.result:
            self.cfg["entries"].append(dialog.result)
            self._persist()
            self._refresh_entries_tree()

    def _selected_entry_id(self) -> Optional[str]:
        selection = self.entries_tree.selection()
        return selection[0] if selection else None

    def _edit_entry(self) -> None:
        entry_id = self._selected_entry_id()
        if not entry_id:
            messagebox.showinfo(APP_TITLE, "Lütfen düzenlemek için bir kayıt seçin.")
            return
        entry = next((e for e in self.cfg["entries"] if e["id"] == entry_id), None)
        if not entry:
            return
        dialog = EntryDialog(self, entry)
        self.wait_window(dialog)
        if dialog.result:
            idx = self.cfg["entries"].index(entry)
            self.cfg["entries"][idx] = dialog.result
            self._persist()
            self._refresh_entries_tree()

    def _delete_entry(self) -> None:
        entry_id = self._selected_entry_id()
        if not entry_id:
            messagebox.showinfo(APP_TITLE, "Lütfen silmek için bir kayıt seçin.")
            return
        if not messagebox.askyesno(APP_TITLE, "Seçili kayıt silinsin mi?"):
            return
        self.cfg["entries"] = [e for e in self.cfg["entries"] if e["id"] != entry_id]
        self._persist()
        self._refresh_entries_tree()

    def _test_entry(self) -> None:
        entry_id = self._selected_entry_id()
        entry = next((e for e in self.cfg["entries"] if e["id"] == entry_id), None)
        sound = entry.get("sound") if entry else "default"
        self._play_test_sound(sound)

    # ---------- Namaz vakitleri sekmesi ----------
    def _build_prayer_tab(self) -> None:
        frame = self._make_scrollable(self.prayer_tab)
        pt = self.cfg["prayer_times"]

        top = ttk.Frame(frame)
        top.pack(fill="x", padx=8, pady=8)

        self.prayer_enabled_var = tk.BooleanVar(value=pt.get("enabled", True))
        ttk.Checkbutton(top, text="Namaz vakitlerine göre otomatik hatırlatma/zil yapılsın",
                         variable=self.prayer_enabled_var,
                         command=self._save_prayer_general_settings).pack(anchor="w")

        city_frame = ttk.Frame(top)
        city_frame.pack(fill="x", pady=8)
        ttk.Label(city_frame, text="İl / İlçe:").pack(side="left")
        self.prayer_city_var = tk.StringVar(value=pt.get("city", "İstanbul"))
        city_entry = ttk.Entry(city_frame, textvariable=self.prayer_city_var, width=25)
        city_entry.pack(side="left", padx=8)
        city_entry.bind("<FocusOut>", lambda e: self._save_prayer_general_settings())
        ttk.Button(city_frame, text="🕌 Bugünün Vakitlerini Göster",
                   command=self._show_today_prayer_times).pack(side="left", padx=12)

        self.prayer_info_var = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.prayer_info_var, foreground=ACCENT_DARK,
                  wraplength=820, justify="left").pack(anchor="w", pady=(4, 0))

        daily_frame = ttk.LabelFrame(frame, text="Günlük Vakit Sesi")
        daily_frame.pack(fill="x", padx=8, pady=8)

        ttk.Label(daily_frame,
                  text="Açtığınız vakit, tam saatinde seçtiğiniz sesi çalar.",
                  foreground="#666666", wraplength=820, justify="left").grid(
            row=0, column=0, columnspan=4, sticky="w", padx=8, pady=(6, 6))

        self.daily_vars: dict[str, dict] = {}
        for i, vakit in enumerate(VAKIT_KEYS, start=1):
            setting = pt["daily"][vakit]

            ttk.Label(daily_frame, text=prayer_service.VAKIT_LABELS[vakit], width=8).grid(
                row=i, column=0, padx=(8, 6), pady=3, sticky="w")

            enabled_var = tk.BooleanVar(value=setting.get("enabled", False))
            ttk.Checkbutton(daily_frame, text="Oku", variable=enabled_var,
                             command=lambda v=vakit: self._save_daily_setting(v)).grid(
                row=i, column=1, padx=6, pady=3, sticky="w")

            sound_var = tk.StringVar(value=setting.get("sound") or "")
            ttk.Entry(daily_frame, textvariable=sound_var, width=34, state="readonly").grid(
                row=i, column=2, padx=(6, 2), pady=3, sticky="we")
            ttk.Button(daily_frame, text="📁 Seç", width=7,
                       command=lambda v=vakit: self._choose_daily_sound(v)).grid(
                row=i, column=3, padx=2, pady=3)
            ttk.Button(daily_frame, text="❌", width=3,
                       command=lambda v=vakit: self._clear_daily_sound(v)).grid(
                row=i, column=4, padx=2, pady=3)
            ttk.Button(daily_frame, text="▶ Test", width=6,
                       command=lambda v=vakit: self._test_daily_sound(v)).grid(
                row=i, column=5, padx=(2, 8), pady=3)

            self.daily_vars[vakit] = {"enabled": enabled_var, "sound": sound_var}

        daily_frame.columnconfigure(2, weight=1)

        friday_frame = ttk.LabelFrame(frame, text="Cuma Namazı (öğle vaktine göre önce/sonra)")
        friday_frame.pack(fill="both", expand=True, padx=8, pady=8)

        ttk.Label(friday_frame,
                  text="Sadece Cuma günleri çalışır. Örn: namazdan 15 dk önce paydos zili, "
                       "namazdan 30 dk sonra mesaiye dönüş zili gibi istediğiniz kadar "
                       "bağımsız kayıt ekleyebilirsiniz.",
                  foreground="#666666", wraplength=820, justify="left").pack(
            anchor="w", padx=8, pady=(6, 0))

        columns = ("enabled", "direction", "minutes", "label", "sound")
        self.friday_tree = ttk.Treeview(friday_frame, columns=columns, show="headings", height=6)
        headers = {"enabled": "Etkin", "direction": "Yön", "minutes": "Dakika",
                   "label": "Etiket", "sound": "Ses"}
        widths = {"enabled": 60, "direction": 70, "minutes": 70, "label": 300, "sound": 200}
        for col in columns:
            self.friday_tree.heading(col, text=headers[col])
            self.friday_tree.column(col, width=widths[col], anchor="w")
        self.friday_tree.tag_configure("oddrow", background=ROW_ODD)
        self.friday_tree.tag_configure("evenrow", background=ROW_EVEN)
        self.friday_tree.pack(fill="both", expand=True, padx=8, pady=8)

        btn_frame = ttk.Frame(friday_frame)
        btn_frame.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btn_frame, text="➕ Ekle", style="Accent.TButton",
                   command=self._add_friday_offset).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="✏️ Düzenle", command=self._edit_friday_offset).pack(
            side="left", padx=4)
        ttk.Button(btn_frame, text="🗑️ Sil", command=self._delete_friday_offset).pack(
            side="left", padx=4)
        ttk.Button(btn_frame, text="▶ Şimdi Çal (Test)", command=self._test_friday_offset).pack(
            side="left", padx=4)

        options_frame = ttk.LabelFrame(frame, text="Genel Ayarlar")
        options_frame.pack(fill="x", padx=8, pady=8)

        self.prayer_topmost_var = tk.BooleanVar(value=pt.get("en_ustte_goster", False))
        ttk.Checkbutton(options_frame, text="Pencereyi En Üstte Göster",
                         variable=self.prayer_topmost_var,
                         command=self._save_prayer_general_settings).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=8, pady=4)

        ttk.Button(options_frame, text="💾 Şuan ki Ayarları Kaydet", style="Accent.TButton",
                   command=self._manual_save_prayer_settings).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=8, pady=(10, 6))

        self._refresh_friday_tree()

    def _save_daily_setting(self, vakit: str) -> None:
        pair = self.daily_vars[vakit]
        self.cfg["prayer_times"]["daily"][vakit] = {
            "enabled": pair["enabled"].get(),
            "sound": pair["sound"].get().strip() or None,
        }
        self._persist()

    def _choose_daily_sound(self, vakit: str) -> None:
        path = filedialog.askopenfilename(
            title="Ses dosyası seç",
            filetypes=[("Ses dosyaları", "*.wav *.mp3 *.ogg *.flac"), ("Tüm dosyalar", "*.*")])
        if not path:
            return
        self.daily_vars[vakit]["sound"].set(path)
        self._save_daily_setting(vakit)

    def _clear_daily_sound(self, vakit: str) -> None:
        self.daily_vars[vakit]["sound"].set("")
        self._save_daily_setting(vakit)

    def _test_daily_sound(self, vakit: str) -> None:
        sound = self.daily_vars[vakit]["sound"].get().strip() or "default"
        self._play_test_sound(sound)

    def _refresh_friday_tree(self) -> None:
        self.friday_tree.delete(*self.friday_tree.get_children())
        for i, offset in enumerate(self.cfg["prayer_times"]["friday_offsets"]):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            self.friday_tree.insert("", "end", iid=offset["id"], tags=(tag,), values=(
                "Evet" if offset.get("enabled", True) else "Hayır",
                "Önce" if offset.get("direction", "before") == "before" else "Sonra",
                offset.get("minutes", 0),
                offset.get("label", ""),
                format_sound(offset.get("sound")),
            ))

    def _selected_friday_offset_id(self) -> Optional[str]:
        selection = self.friday_tree.selection()
        return selection[0] if selection else None

    def _add_friday_offset(self) -> None:
        dialog = FridayOffsetDialog(self)
        self.wait_window(dialog)
        if dialog.result:
            self.cfg["prayer_times"]["friday_offsets"].append(dialog.result)
            self._persist()
            self._refresh_friday_tree()

    def _edit_friday_offset(self) -> None:
        offset_id = self._selected_friday_offset_id()
        if not offset_id:
            messagebox.showinfo(APP_TITLE, "Lütfen düzenlemek için bir kayıt seçin.")
            return
        offset = next((o for o in self.cfg["prayer_times"]["friday_offsets"]
                       if o["id"] == offset_id), None)
        if not offset:
            return
        dialog = FridayOffsetDialog(self, offset)
        self.wait_window(dialog)
        if dialog.result:
            idx = self.cfg["prayer_times"]["friday_offsets"].index(offset)
            self.cfg["prayer_times"]["friday_offsets"][idx] = dialog.result
            self._persist()
            self._refresh_friday_tree()

    def _delete_friday_offset(self) -> None:
        offset_id = self._selected_friday_offset_id()
        if not offset_id:
            messagebox.showinfo(APP_TITLE, "Lütfen silmek için bir kayıt seçin.")
            return
        if not messagebox.askyesno(APP_TITLE, "Seçili kayıt silinsin mi?"):
            return
        self.cfg["prayer_times"]["friday_offsets"] = [
            o for o in self.cfg["prayer_times"]["friday_offsets"] if o["id"] != offset_id]
        self._persist()
        self._refresh_friday_tree()

    def _test_friday_offset(self) -> None:
        offset_id = self._selected_friday_offset_id()
        offset = next((o for o in self.cfg["prayer_times"]["friday_offsets"]
                       if o["id"] == offset_id), None)
        if not offset:
            messagebox.showinfo(APP_TITLE, "Lütfen test etmek için bir kayıt seçin.")
            return
        self._play_test_sound(offset.get("sound") or "default")

    def _save_prayer_general_settings(self) -> None:
        pt = self.cfg["prayer_times"]
        pt["enabled"] = self.prayer_enabled_var.get()
        pt["city"] = self.prayer_city_var.get().strip()
        pt["en_ustte_goster"] = self.prayer_topmost_var.get()
        self.attributes("-topmost", pt["en_ustte_goster"])
        self._persist()

    def _manual_save_prayer_settings(self) -> None:
        self._save_prayer_general_settings()
        messagebox.showinfo(APP_TITLE, "Namaz vakti ayarları kaydedildi.")

    def _show_today_prayer_times(self) -> None:
        city = self.prayer_city_var.get().strip()
        if not city:
            messagebox.showinfo(APP_TITLE, "Lütfen önce il/ilçe girin.")
            return
        self.prayer_info_var.set("Sorgulanıyor...")
        self.update_idletasks()
        timings, from_network = prayer_service.get_cached_or_fetch_day(
            city, target_date=date.today())
        if not timings:
            self.prayer_info_var.set("Vakitler alınamadı. İnternet bağlantınızı kontrol edin.")
            return
        parts = [f"{prayer_service.VAKIT_LABELS[v]}: {timings[v]}"
                 for v in VAKIT_KEYS if v in timings]
        self.prayer_info_var.set("  |  ".join(parts))

    # ---------- Ses ayarları: varsayılan ses + ses seviyesi ----------
    def _choose_default_sound(self) -> None:
        path = filedialog.askopenfilename(
            title="Varsayılan ses dosyası seç",
            filetypes=[("Ses dosyaları", "*.wav *.mp3 *.ogg *.flac"), ("Tüm dosyalar", "*.*")])
        if path:
            self.default_sound_var.set(path)
            self.cfg["default_sound"] = path
            self._persist()

    def _clear_default_sound(self) -> None:
        self.default_sound_var.set("(Seçilmedi - lütfen bir ses dosyası seçin)")
        self.cfg["default_sound"] = None
        self._persist()

    def _save_volume(self) -> None:
        self.cfg["volume"] = self.volume_var.get() / 100.0
        self._persist()

    def _test_default_sound(self) -> None:
        self._play_test_sound(self.cfg.get("default_sound", "default"))

    def _choose_fire_button_sound(self) -> None:
        path = filedialog.askopenfilename(
            title="Yangın butonu için ses dosyası seç",
            filetypes=[("Ses dosyaları", "*.wav *.mp3 *.ogg *.flac"), ("Tüm dosyalar", "*.*")])
        if path:
            self.fire_button_sound_var.set(path)
            self.cfg["fire_button_sound"] = path
            self._persist()

    def _clear_fire_button_sound(self) -> None:
        self.fire_button_sound_var.set("(Seçilmedi - varsayılan zil sesi çalınır)")
        self.cfg["fire_button_sound"] = None
        self._persist()

    # ---------- Ayarları dışa/içe aktarma (kod ile, eşleştirme gibi) ----------
    def _export_config(self) -> None:
        ExportCodeDialog(self, self.remote_control, self.cfg)

    def _import_config(self) -> None:
        dialog = ImportCodeDialog(self, self.remote_control)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        host_name, config = dialog.result
        if not messagebox.askyesno(
                APP_TITLE,
                f"'{host_name}' cihazından alınan ayarlar, mevcut TÜM ayarların (zil "
                "kayıtları, namaz vakitleri, tatil günleri, sesler) üzerine yazacak. "
                "Devam edilsin mi?"):
            return
        # complete_config(), içe aktarılan veri eksik/elle düzenlenmiş olsa
        # bile (ör. eski bir sürümden) her alanın var olduğunu garanti eder -
        # aksi halde sekmeler yeniden kurulurken KeyError ile çöker.
        self.cfg = complete_config(config)
        self._persist()
        self._rebuild_all_tabs()
        self._log(f"Ayarlar '{host_name}' cihazından içe aktarıldı.")

    # ---------- Genel sekmesi: tatil günleri ----------
    def _refresh_holidays_tree(self) -> None:
        self.holidays_tree.delete(*self.holidays_tree.get_children())
        holidays = sorted(self.cfg.get("holidays", []), key=lambda h: h.get("date", ""))
        for i, holiday in enumerate(holidays):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            ring_text = f"{holiday.get('ring_time')} - {format_sound(holiday.get('ring_sound'))}" \
                if holiday.get("ring") else "(Zil çalmaz)"
            self.holidays_tree.insert("", "end", iid=holiday["date"], tags=(tag,), values=(
                format_holiday_date(holiday.get("date", "")), holiday.get("label", ""), ring_text))

    def _add_holiday(self) -> None:
        dialog = HolidayDialog(self)
        self.wait_window(dialog)
        if dialog.result:
            self.cfg.setdefault("holidays", [])
            self.cfg["holidays"] = [h for h in self.cfg["holidays"]
                                     if h["date"] != dialog.result["date"]]
            self.cfg["holidays"].append(dialog.result)
            self._persist()
            self._refresh_holidays_tree()

    def _edit_holiday(self) -> None:
        selection = self.holidays_tree.selection()
        if not selection:
            messagebox.showinfo(APP_TITLE, "Lütfen düzenlemek için bir tarih seçin.")
            return
        date_iso = selection[0]
        holiday = next((h for h in self.cfg.get("holidays", []) if h["date"] == date_iso), None)
        if holiday is None:
            return
        dialog = HolidayDialog(self, holiday=holiday)
        self.wait_window(dialog)
        if dialog.result:
            self.cfg["holidays"] = [h for h in self.cfg["holidays"] if h["date"] != date_iso]
            self.cfg["holidays"].append(dialog.result)
            self._persist()
            self._refresh_holidays_tree()

    def _delete_holiday(self) -> None:
        selection = self.holidays_tree.selection()
        if not selection:
            messagebox.showinfo(APP_TITLE, "Lütfen silmek için bir tarih seçin.")
            return
        if not messagebox.askyesno(APP_TITLE, "Seçili tatil günü silinsin mi?"):
            return
        date_iso = selection[0]
        self.cfg["holidays"] = [h for h in self.cfg["holidays"] if h["date"] != date_iso]
        self._persist()
        self._refresh_holidays_tree()


class RemoteSettingsWindow(tk.Toplevel, ConfigTabsMixin):
    """Eşleşmiş bir uzak cihazın ayarlarını, o cihazın kendi arayüzüyle
    AYNI görünümde (sekmeler, tablolar - ham JSON değil) gösterip
    düzenleme penceresi. Her değişiklik anında 'set_config' komutuyla
    karşı cihaza gönderilir (yerelde olduğu gibi anlık kaydedilir).

    Ses çıkış cihazı seçimi, sistem tepsisi, Windows açılışında otomatik
    başlatma ve log klasörü KASITLI OLARAK burada YOKTUR - bunlar yalnızca
    ayarı değiştirdiğiniz fiziksel makinede anlamlıdır (bkz.
    ConfigTabsMixin'in üstündeki not)."""

    def __init__(self, parent, peer: "remote_control.PairedDevice", config_data: dict,
                 manager: "remote_control.RemoteControlManager", on_log: Callable[[str], None]):
        super().__init__(parent)
        self.title(f"Uzak Ayarlar - {peer.name}")
        self.configure(bg=BG)
        self.geometry("900x680")
        self.minsize(760, 520)
        self.transient(parent)
        self.peer = peer
        self.manager = manager
        # ConfigTabsMixin'in bazı ortak metodları (ör. _export_config/
        # _import_config, kod tabanlı ayar aktarımı için) App ile
        # RemoteSettingsWindow arasında ortak bir isimle "remote_control"
        # yöneticisine erişmek ister - burada App'teki gibi aynı isimle
        # (manager'a) bir takma ad tanımlanıyor.
        self.remote_control = manager
        self.on_log = on_log
        self.cfg = config_data

        ttk.Label(
            self, text=f"🔗 '{peer.name}' cihazının ayarları - burada yaptığınız her değişiklik "
                       "anında o cihaza gönderilir.",
            wraplength=860, justify="left", background=BG,
            font=FONT_BOLD).pack(anchor="w", padx=12, pady=(10, 2))
        ttk.Label(
            self, text="Not: Bir ses dosyası seçerseniz, seçtiğiniz dosya BU bilgisayardaki bir "
                       f"dosyadır - '{peer.name}' cihazı o dosyaya erişemeyebilir. Ses dosyalarını "
                       "mümkünse doğrudan ilgili cihazın kendisinde ayarlayın.",
            wraplength=860, justify="left", background=BG,
            foreground="#8a5a00").pack(anchor="w", padx=12, pady=(0, 8))

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.entries_tab = ttk.Frame(notebook)
        self.prayer_tab = ttk.Frame(notebook)
        self.audio_tab = ttk.Frame(notebook)
        self.general_tab = ttk.Frame(notebook)
        notebook.add(self.entries_tab, text="🔔 Zil Programı")
        notebook.add(self.prayer_tab, text="🕌 Namaz Vakitleri")
        notebook.add(self.audio_tab, text="🔊 Ses Ayarları")
        notebook.add(self.general_tab, text="⚙️ Genel")

        self._build_entries_tab()
        self._build_prayer_tab()
        self._build_audio_tab()
        self._build_general_tab()

    # ---------- Bu pencereye özel: cihaz seçimi olmayan ses sekmesi ----------
    def _build_audio_tab(self) -> None:
        frame = self.audio_tab
        pad = {"padx": 10, "pady": 8}

        ttk.Label(frame, text="Çalınacak zil sesi:").grid(row=0, column=0, sticky="w", **pad)
        self.default_sound_var = tk.StringVar(
            value=self.cfg.get("default_sound") or "(Seçilmedi - lütfen bir ses dosyası seçin)")
        ttk.Entry(frame, textvariable=self.default_sound_var, width=40, state="readonly").grid(
            row=0, column=1, sticky="we", **pad)
        ttk.Button(frame, text="📁 Seç...", command=self._choose_default_sound).grid(
            row=0, column=2, sticky="w", **pad)
        ttk.Button(frame, text="❌ Kaldır", command=self._clear_default_sound).grid(
            row=0, column=3, sticky="w", **pad)

        ttk.Label(frame, text="Ses seviyesi:").grid(row=1, column=0, sticky="w", **pad)
        self.volume_var = tk.DoubleVar(value=self.cfg.get("volume", 1.0) * 100)
        volume_scale = ttk.Scale(frame, from_=0, to=100, variable=self.volume_var,
                                  orient="horizontal", command=lambda v: self._save_volume())
        volume_scale.grid(row=1, column=1, sticky="we", **pad)

        ttk.Button(frame, text="🔊 Test Sesi Çal (uzak cihazda)", style="Accent.TButton",
                   command=self._test_default_sound).grid(row=2, column=1, sticky="w", **pad)

        ttk.Separator(frame, orient="horizontal").grid(
            row=3, column=0, columnspan=3, sticky="we", padx=10, pady=10)

        ttk.Label(frame, text="🔥 Yangın butonu sesi:").grid(row=4, column=0, sticky="w", **pad)
        self.fire_button_sound_var = tk.StringVar(
            value=self.cfg.get("fire_button_sound")
            or "(Seçilmedi - varsayılan zil sesi çalınır)")
        ttk.Entry(frame, textvariable=self.fire_button_sound_var, width=40, state="readonly").grid(
            row=4, column=1, sticky="we", **pad)
        ttk.Button(frame, text="📁 Seç...", command=self._choose_fire_button_sound).grid(
            row=4, column=2, sticky="w", **pad)
        ttk.Button(frame, text="❌ Kaldır", command=self._clear_fire_button_sound).grid(
            row=4, column=3, sticky="w", **pad)

        frame.columnconfigure(1, weight=1)

    # ---------- Bu pencereye özel: tepsi/otomatik başlatma olmayan Genel sekmesi ----------
    def _build_general_tab(self) -> None:
        frame = self.general_tab
        ttk.Label(
            frame, text="Sistem tepsisi, Windows açılışında otomatik başlatma ve log klasörü "
                       "gibi bu bilgisayara özgü ayarlar burada gösterilmez - bunlar yalnızca "
                       f"'{self.peer.name}' cihazının kendisinde değiştirilebilir.",
            foreground="#666666", wraplength=820, justify="left").pack(
            anchor="w", padx=10, pady=(12, 8))

        backup_frame = ttk.LabelFrame(frame, text="Ayarları Kod ile Aktar")
        backup_frame.pack(fill="x", padx=10, pady=(0, 8))
        backup_btn_frame = ttk.Frame(backup_frame)
        backup_btn_frame.pack(fill="x", padx=8, pady=8)
        ttk.Button(backup_btn_frame,
                   text=f"🔑 Kod Oluştur ('{self.peer.name}' ayarlarını paylaş)",
                   command=self._export_config).pack(side="left", padx=4)
        ttk.Button(backup_btn_frame,
                   text=f"📥 Kod ile İçe Aktar ('{self.peer.name}' cihazına gönder)",
                   command=self._import_config).pack(side="left", padx=4)

        holidays_frame = ttk.LabelFrame(
            frame, text="Tatil Günleri (normal program bu tarihlerde çalmaz)")
        holidays_frame.pack(fill="both", expand=True, padx=10, pady=8)

        columns = ("date", "label", "ring")
        self.holidays_tree = ttk.Treeview(holidays_frame, columns=columns, show="headings",
                                           height=8)
        self.holidays_tree.heading("date", text="Tarih")
        self.holidays_tree.heading("label", text="Açıklama")
        self.holidays_tree.heading("ring", text="Özel Zil")
        self.holidays_tree.column("date", width=110, anchor="w")
        self.holidays_tree.column("label", width=300, anchor="w")
        self.holidays_tree.column("ring", width=180, anchor="w")
        self.holidays_tree.tag_configure("oddrow", background=ROW_ODD)
        self.holidays_tree.tag_configure("evenrow", background=ROW_EVEN)
        self.holidays_tree.pack(fill="both", expand=True, padx=8, pady=8)
        self.holidays_tree.bind("<Double-1>", lambda e: self._edit_holiday())

        btn_frame = ttk.Frame(holidays_frame)
        btn_frame.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btn_frame, text="➕ Ekle", style="Accent.TButton",
                   command=self._add_holiday).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="✏️ Düzenle", command=self._edit_holiday).pack(
            side="left", padx=4)
        ttk.Button(btn_frame, text="🗑️ Sil", command=self._delete_holiday).pack(side="left", padx=4)

        self._refresh_holidays_tree()

    # ---------- Yerel yerine ağ üzerinden kaydet/çal/logla ----------
    def _persist(self) -> None:
        threading.Thread(target=self._push_worker, daemon=True).start()

    def _rebuild_all_tabs(self) -> None:
        """_import_config() sonrası self.cfg TAMAMEN değiştiği için (ör.
        farklı bir cihazdan/eski bir yedekten), önceden kurulmuş ağaç ve
        alan widget'ları artık eski veriyi gösterir - App._rebuild_all_tabs
        ile aynı desen: sekme içeriklerini yıkıp yeniden kur."""
        for tab in (self.entries_tab, self.prayer_tab, self.audio_tab, self.general_tab):
            for child in tab.winfo_children():
                child.destroy()
        self._build_entries_tab()
        self._build_prayer_tab()
        self._build_audio_tab()
        self._build_general_tab()

    def _push_worker(self) -> None:
        try:
            result = self.manager.send_command(self.peer, {"cmd": "set_config",
                                                             "config": self.cfg})
        except Exception as exc:
            self.on_log(f"'{self.peer.name}' cihazına ayarlar gönderilemedi: {exc}")
            return
        if not result.get("ok"):
            self.on_log(f"'{self.peer.name}' ayarları reddetti: {result.get('error')}")

    def _log(self, message: str) -> None:
        self.on_log(message)

    def _play_test_sound(self, sound: Optional[str]) -> None:
        def worker():
            try:
                result = self.manager.send_command(self.peer, {"cmd": "ring_now", "sound": sound})
            except Exception as exc:
                self.on_log(f"'{self.peer.name}' cihazında çalınamadı: {exc}")
                return
            if result.get("ok"):
                self.on_log(f"'{self.peer.name}' cihazında test sesi çalındı.")
            else:
                self.on_log(f"'{self.peer.name}' reddetti: {result.get('error')}")
        threading.Thread(target=worker, daemon=True).start()


class App(tk.Tk):
    def __init__(self, instance: Optional[SingleInstance] = None):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("860x660")
        self.minsize(760, 560)
        self.configure(bg=BG)

        self._setup_style()

        self.cfg = load_config()
        self._file_logger = app_logging.get_logger()
        self._tray: Optional["tray_icon.TrayIcon"] = None
        self._instance = instance
        if self._instance is not None:
            self.after(200, self._poll_instance_queue)

        # _build_ui() (aşağıda) "Uzaktan Erişim" sekmesini de kurar ve bu,
        # self.remote_control.paired_devices'a erişir - bu yüzden
        # RemoteControlManager _build_ui()'dan ÖNCE oluşturulmalıdır.
        self.remote_control = remote_control.RemoteControlManager(
            get_config=lambda: self.cfg,
            apply_remote_config=self._apply_remote_config,
            ring_now=self._remote_ring_now,
            stop_ringing=audio_player.stop,
            on_pairing_request=self._on_remote_pairing_request,
            on_log=self._log,
            on_devices_changed=self._save_paired_devices,
            initial_paired_devices=[remote_control.PairedDevice.from_json(d)
                                     for d in load_paired_devices_raw()],
        )

        self._build_ui()
        self._refresh_entries_tree()
        self._refresh_friday_tree()
        self._refresh_devices()
        self._refresh_holidays_tree()
        self._update_clock()

        if self.cfg["prayer_times"].get("en_ustte_goster"):
            self.attributes("-topmost", True)

        if self.cfg.get("minimize_to_tray", True):
            self._start_tray()

        self.scheduler = BellScheduler(get_config=lambda: self.cfg, on_log=self._log)
        self.scheduler.start()

        try:
            self.remote_control.start()
        except OSError as exc:
            self._log(f"Uzaktan erişim başlatılamadı (port kullanımda olabilir): {exc}")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        if not self.cfg.get("default_sound"):
            self.after(300, self._prompt_first_run_sound)

    # ---------- Görsel tema ----------
    def _setup_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=BG)
        style.configure("TLabelframe", background=BG, bordercolor="#c9d3ce")
        style.configure("TLabelframe.Label", background=BG, font=FONT_BOLD, foreground=ACCENT_DARK)
        style.configure("TLabel", background=BG, font=FONT)
        style.configure("TCheckbutton", background=BG, font=FONT, focuscolor=BG)
        style.configure("TRadiobutton", background=BG, font=FONT, focuscolor=BG)
        style.configure("TNotebook", background=BG, tabmargins=(4, 6, 4, 0))
        style.configure("TNotebook.Tab", font=FONT_BOLD, padding=(14, 8))
        style.map("TNotebook.Tab", background=[("selected", ACCENT)],
                  foreground=[("selected", "white")])
        style.configure("TButton", font=FONT, padding=6)
        style.configure("Accent.TButton", font=FONT_BOLD, padding=6,
                         background=ACCENT, foreground="white")
        style.map("Accent.TButton", background=[("active", ACCENT_DARK)])
        style.configure("Header.TFrame", background=ACCENT_DARK)
        style.configure("HeaderTitle.TLabel", background=ACCENT_DARK, foreground="white",
                         font=("Segoe UI", 16, "bold"))
        style.configure("HeaderSubtitle.TLabel", background=ACCENT_DARK, foreground="#cfe8da",
                         font=("Segoe UI", 9))
        style.configure("HeaderClock.TLabel", background=ACCENT_DARK, foreground="white",
                         font=("Segoe UI", 12, "bold"))
        style.configure("Treeview", rowheight=26, font=FONT, fieldbackground="white")
        style.configure("Treeview.Heading", font=FONT_BOLD)
        style.map("Treeview", background=[("selected", ACCENT)],
                  foreground=[("selected", "white")])

    def _prompt_first_run_sound(self) -> None:
        messagebox.showinfo(
            APP_TITLE,
            "Programın kendi ürettiği bir zil sesi yoktur.\n\n"
            "Lütfen bilgisayarınızdan çalınmasını istediğiniz zil sesi dosyasını "
            "(wav/mp3/ogg/flac) seçin.")
        self._choose_default_sound()

    # ---------- UI kurulumu ----------
    def _build_ui(self) -> None:
        self._build_header()

        notebook = self.notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=(6, 10))

        self.entries_tab = ttk.Frame(notebook)
        self.prayer_tab = ttk.Frame(notebook)
        self.audio_tab = ttk.Frame(notebook)
        self.general_tab = ttk.Frame(notebook)
        self.stats_tab = ttk.Frame(notebook)
        self.remote_tab = ttk.Frame(notebook)
        notebook.add(self.entries_tab, text="🔔 Zil Programı")
        notebook.add(self.prayer_tab, text="🕌 Namaz Vakitleri")
        notebook.add(self.audio_tab, text="🔊 Ses Ayarları")
        notebook.add(self.general_tab, text="⚙️ Genel")
        notebook.add(self.stats_tab, text="📊 İstatistikler")
        notebook.add(self.remote_tab, text="🔗 Uzaktan Erişim")

        self._build_entries_tab()
        self._build_prayer_tab()
        self._build_audio_tab()
        self._build_general_tab()
        self._build_stats_tab()
        self._build_remote_tab()

        # İstatistikler sekmesine her geçildiğinde tazele - sürekli
        # zamanlayıcıyla değil, yalnızca gerçekten görüntülenirken diskten
        # okunur.
        notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        log_frame = ttk.LabelFrame(self, text="📋 Kayıtlar")
        log_frame.pack(fill="both", expand=False, padx=10, pady=(0, 10))
        self.log_text = tk.Text(log_frame, height=7, state="disabled", wrap="word",
                                 bg="white", relief="flat", font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True, padx=6, pady=6)
        self.log_text.tag_configure("ring", foreground=ACCENT_DARK, font=("Consolas", 9, "bold"))
        self.log_text.tag_configure("error", foreground="#b3261e")
        self.log_text.tag_configure("info", foreground="#555555")

    def _make_scrollable(self, parent: ttk.Frame) -> ttk.Frame:
        """İçeriği pencere yüksekliğini aşan sekmeler için (ör. Namaz
        Vakitleri) dikey kaydırmalı bir alan kurar; fare tekerleği ve
        kaydırma çubuğuyla alttaki içeriğe (butonlar, tablolar) erişilebilir.
        Döndürülen frame'e widget'lar normal şekilde eklenir."""
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        inner = ttk.Frame(canvas)
        inner_window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event) -> None:
            canvas.itemconfig(inner_window, width=event.width)

        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event) -> None:
            if event.num == 5 or event.delta < 0:
                canvas.yview_scroll(1, "units")
            elif event.num == 4 or event.delta > 0:
                canvas.yview_scroll(-1, "units")

        def _bind_mousewheel(_event=None) -> None:
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
            canvas.bind_all("<Button-4>", _on_mousewheel)
            canvas.bind_all("<Button-5>", _on_mousewheel)

        def _unbind_mousewheel(_event=None) -> None:
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", _bind_mousewheel)
        canvas.bind("<Leave>", _unbind_mousewheel)

        return inner

    def _build_header(self) -> None:
        header = ttk.Frame(self, style="Header.TFrame")
        header.pack(fill="x")

        title_box = ttk.Frame(header, style="Header.TFrame")
        title_box.pack(side="left", padx=18, pady=12)
        ttk.Label(title_box, text="🔔 Ceselsan Zil Takip Programı",
                  style="HeaderTitle.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="Okul / Kurum Zil ve Namaz Vakti Otomasyonu",
                  style="HeaderSubtitle.TLabel").pack(anchor="w")

        self.clock_var = tk.StringVar()
        ttk.Label(header, textvariable=self.clock_var, style="HeaderClock.TLabel").pack(
            side="right", padx=18)

        fire_btn = tk.Button(header, text="🔥 YANGIN", font=FONT_BOLD, fg="white",
                              bg="#b3261e", activebackground="#8a1c17", activeforeground="white",
                              relief="flat", padx=14, pady=6, cursor="hand2",
                              command=self._ring_fire_button)
        fire_btn.pack(side="right", padx=8)

    def _ring_fire_button(self) -> None:
        sound = self.cfg.get("fire_button_sound") or "default"
        try:
            audio_player.play_file(sound, self.cfg.get("output_device"),
                                    self.cfg.get("default_sound"), self.cfg.get("volume", 1.0))
            self._log("Zil çalıyor: Yangın Butonu")
            ring_history.record_ring("Yangın Butonu", "fire_button")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Ses çalınamadı: {exc}")
            ring_history.record_ring("Yangın Butonu", "fire_button", success=False,
                                      error=str(exc))

    # ---------- İstatistikler sekmesi ----------
    def _on_tab_changed(self, _event=None) -> None:
        try:
            current = self.notebook.select()
            if current and self.notebook.nametowidget(current) is self.stats_tab:
                self._refresh_stats()
        except tk.TclError:
            pass

    def _build_stats_tab(self) -> None:
        frame = self.stats_tab

        cards_frame = ttk.Frame(frame)
        cards_frame.pack(fill="x", padx=10, pady=10)
        self.stats_today_var = tk.StringVar(value="0")
        self.stats_week_var = tk.StringVar(value="0")
        self.stats_month_var = tk.StringVar(value="0")
        for i, (title, var) in enumerate((
                ("Bugün", self.stats_today_var),
                ("Bu Hafta", self.stats_week_var),
                ("Bu Ay", self.stats_month_var))):
            card = ttk.LabelFrame(cards_frame, text=f"{title} Çalan Zil Sayısı")
            card.grid(row=0, column=i, padx=8, sticky="we")
            ttk.Label(card, textvariable=var, font=("Segoe UI", 24, "bold"),
                      foreground=ACCENT_DARK).pack(padx=24, pady=12)
        cards_frame.columnconfigure(0, weight=1)
        cards_frame.columnconfigure(1, weight=1)
        cards_frame.columnconfigure(2, weight=1)

        ttk.Button(frame, text="🔄 Yenile", command=self._refresh_stats).pack(
            anchor="w", padx=10, pady=(0, 8))

        history_frame = ttk.LabelFrame(frame, text="Son Zil Kayıtları (en yeniden en eskiye)")
        history_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        columns = ("time", "label", "kind", "status")
        self.stats_tree = ttk.Treeview(history_frame, columns=columns, show="headings",
                                        height=14)
        headers = {"time": "Tarih/Saat", "label": "Etiket", "kind": "Tür", "status": "Durum"}
        widths = {"time": 150, "label": 260, "kind": 150, "status": 200}
        for col in columns:
            self.stats_tree.heading(col, text=headers[col])
            self.stats_tree.column(col, width=widths[col], anchor="w")
        self.stats_tree.tag_configure("oddrow", background=ROW_ODD)
        self.stats_tree.tag_configure("evenrow", background=ROW_EVEN)
        self.stats_tree.tag_configure("failed", foreground="#b3261e")
        self.stats_tree.pack(fill="both", expand=True, padx=8, pady=8)

        self._refresh_stats()

    def _refresh_stats(self) -> None:
        entries = ring_history.load_history()
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)

        today_count = week_count = month_count = 0
        parsed: list[tuple[datetime, dict]] = []
        for entry in entries:
            try:
                t = datetime.fromisoformat(entry["time"])
            except (KeyError, ValueError, TypeError):
                continue
            parsed.append((t, entry))
            d = t.date()
            if d == today:
                today_count += 1
            if d >= week_start:
                week_count += 1
            if d >= month_start:
                month_count += 1

        self.stats_today_var.set(str(today_count))
        self.stats_week_var.set(str(week_count))
        self.stats_month_var.set(str(month_count))

        self.stats_tree.delete(*self.stats_tree.get_children())
        parsed.sort(key=lambda pair: pair[0], reverse=True)
        for i, (t, entry) in enumerate(parsed[:300]):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            success = entry.get("success", True)
            tags = (tag,) if success else (tag, "failed")
            status = "✅ Çaldı" if success else f"❌ Hata: {entry.get('error', 'bilinmiyor')}"
            kind = entry.get("kind", "")
            self.stats_tree.insert("", "end", tags=tags, values=(
                t.strftime("%d.%m.%Y %H:%M:%S"), entry.get("label", ""),
                RING_KIND_LABELS.get(kind, kind), status))

    def _update_clock(self) -> None:
        now = datetime.now()
        gun = DAY_NAMES[now.weekday()]
        self.clock_var.set(f"{now.strftime('%d.%m.%Y')}  {gun}   {now.strftime('%H:%M:%S')}")
        self.after(1000, self._update_clock)

    def _build_entries_tab(self) -> None:
        frame = self.entries_tab
        columns = ("enabled", "label", "time", "days", "sound")
        self.entries_tree = ttk.Treeview(frame, columns=columns, show="headings", height=12)
        headers = {"enabled": "Etkin", "label": "Etiket", "time": "Saat",
                   "days": "Günler", "sound": "Ses"}
        widths = {"enabled": 60, "label": 220, "time": 70, "days": 160, "sound": 220}
        for col in columns:
            self.entries_tree.heading(col, text=headers[col])
            self.entries_tree.column(col, width=widths[col], anchor="w")
        self.entries_tree.tag_configure("oddrow", background=ROW_ODD)
        self.entries_tree.tag_configure("evenrow", background=ROW_EVEN)
        self.entries_tree.pack(fill="both", expand=True, padx=8, pady=8)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btn_frame, text="➕ Ekle", style="Accent.TButton",
                   command=self._add_entry).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="✏️ Düzenle", command=self._edit_entry).pack(
            side="left", padx=4)
        ttk.Button(btn_frame, text="🗑️ Sil", command=self._delete_entry).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="▶ Şimdi Çal (Test)", command=self._test_entry).pack(
            side="left", padx=4)

    def _build_prayer_tab(self) -> None:
        frame = self._make_scrollable(self.prayer_tab)
        pt = self.cfg["prayer_times"]

        top = ttk.Frame(frame)
        top.pack(fill="x", padx=8, pady=8)

        self.prayer_enabled_var = tk.BooleanVar(value=pt.get("enabled", True))
        ttk.Checkbutton(top, text="Namaz vakitlerine göre otomatik hatırlatma/zil yapılsın",
                         variable=self.prayer_enabled_var,
                         command=self._save_prayer_general_settings).pack(anchor="w")

        city_frame = ttk.Frame(top)
        city_frame.pack(fill="x", pady=8)
        ttk.Label(city_frame, text="İl / İlçe:").pack(side="left")
        self.prayer_city_var = tk.StringVar(value=pt.get("city", "İstanbul"))
        city_entry = ttk.Entry(city_frame, textvariable=self.prayer_city_var, width=25)
        city_entry.pack(side="left", padx=8)
        city_entry.bind("<FocusOut>", lambda e: self._save_prayer_general_settings())
        ttk.Button(city_frame, text="🕌 Bugünün Vakitlerini Göster",
                   command=self._show_today_prayer_times).pack(side="left", padx=12)

        self.prayer_info_var = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.prayer_info_var, foreground=ACCENT_DARK,
                  wraplength=820, justify="left").pack(anchor="w", pady=(4, 0))

        daily_frame = ttk.LabelFrame(frame, text="Günlük Vakit Sesi")
        daily_frame.pack(fill="x", padx=8, pady=8)

        ttk.Label(daily_frame,
                  text="Açtığınız vakit, tam saatinde seçtiğiniz sesi çalar.",
                  foreground="#666666", wraplength=820, justify="left").grid(
            row=0, column=0, columnspan=4, sticky="w", padx=8, pady=(6, 6))

        self.daily_vars: dict[str, dict] = {}
        for i, vakit in enumerate(VAKIT_KEYS, start=1):
            setting = pt["daily"][vakit]

            ttk.Label(daily_frame, text=prayer_service.VAKIT_LABELS[vakit], width=8).grid(
                row=i, column=0, padx=(8, 6), pady=3, sticky="w")

            enabled_var = tk.BooleanVar(value=setting.get("enabled", False))
            ttk.Checkbutton(daily_frame, text="Oku", variable=enabled_var,
                             command=lambda v=vakit: self._save_daily_setting(v)).grid(
                row=i, column=1, padx=6, pady=3, sticky="w")

            sound_var = tk.StringVar(value=setting.get("sound") or "")
            ttk.Entry(daily_frame, textvariable=sound_var, width=34, state="readonly").grid(
                row=i, column=2, padx=(6, 2), pady=3, sticky="we")
            ttk.Button(daily_frame, text="📁 Seç", width=7,
                       command=lambda v=vakit: self._choose_daily_sound(v)).grid(
                row=i, column=3, padx=2, pady=3)
            ttk.Button(daily_frame, text="❌", width=3,
                       command=lambda v=vakit: self._clear_daily_sound(v)).grid(
                row=i, column=4, padx=2, pady=3)
            ttk.Button(daily_frame, text="▶ Test", width=6,
                       command=lambda v=vakit: self._test_daily_sound(v)).grid(
                row=i, column=5, padx=(2, 8), pady=3)

            self.daily_vars[vakit] = {"enabled": enabled_var, "sound": sound_var}

        daily_frame.columnconfigure(2, weight=1)

        friday_frame = ttk.LabelFrame(frame, text="Cuma Namazı (öğle vaktine göre önce/sonra)")
        friday_frame.pack(fill="both", expand=True, padx=8, pady=8)

        ttk.Label(friday_frame,
                  text="Sadece Cuma günleri çalışır. Örn: namazdan 15 dk önce paydos zili, "
                       "namazdan 30 dk sonra mesaiye dönüş zili gibi istediğiniz kadar "
                       "bağımsız kayıt ekleyebilirsiniz.",
                  foreground="#666666", wraplength=820, justify="left").pack(
            anchor="w", padx=8, pady=(6, 0))

        columns = ("enabled", "direction", "minutes", "label", "sound")
        self.friday_tree = ttk.Treeview(friday_frame, columns=columns, show="headings", height=6)
        headers = {"enabled": "Etkin", "direction": "Yön", "minutes": "Dakika",
                   "label": "Etiket", "sound": "Ses"}
        widths = {"enabled": 60, "direction": 70, "minutes": 70, "label": 300, "sound": 200}
        for col in columns:
            self.friday_tree.heading(col, text=headers[col])
            self.friday_tree.column(col, width=widths[col], anchor="w")
        self.friday_tree.tag_configure("oddrow", background=ROW_ODD)
        self.friday_tree.tag_configure("evenrow", background=ROW_EVEN)
        self.friday_tree.pack(fill="both", expand=True, padx=8, pady=8)

        btn_frame = ttk.Frame(friday_frame)
        btn_frame.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btn_frame, text="➕ Ekle", style="Accent.TButton",
                   command=self._add_friday_offset).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="✏️ Düzenle", command=self._edit_friday_offset).pack(
            side="left", padx=4)
        ttk.Button(btn_frame, text="🗑️ Sil", command=self._delete_friday_offset).pack(
            side="left", padx=4)
        ttk.Button(btn_frame, text="▶ Şimdi Çal (Test)", command=self._test_friday_offset).pack(
            side="left", padx=4)

        ttk.Label(frame,
                  text="Not: Kıble yönü bu programın kapsamı dışındadır (zil/ses çalma amaçlı "
                       "bir araçtır, pusula değil).",
                  foreground="#666666", wraplength=820, justify="left").pack(
            anchor="w", padx=10, pady=(0, 4))

        options_frame = ttk.LabelFrame(frame, text="Genel Ayarlar")
        options_frame.pack(fill="x", padx=8, pady=8)

        self.prayer_topmost_var = tk.BooleanVar(value=pt.get("en_ustte_goster", False))
        ttk.Checkbutton(options_frame, text="Pencereyi En Üstte Göster",
                         variable=self.prayer_topmost_var,
                         command=self._save_prayer_general_settings).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=8, pady=4)

        ttk.Button(options_frame, text="💾 Şuan ki Ayarları Kaydet", style="Accent.TButton",
                   command=self._manual_save_prayer_settings).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=8, pady=(10, 6))

    def _build_audio_tab(self) -> None:
        frame = self.audio_tab
        pad = {"padx": 10, "pady": 8}

        ttk.Label(frame, text="Çıkış cihazı (hoparlör):").grid(row=0, column=0, sticky="w", **pad)
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(frame, textvariable=self.device_var, width=45,
                                          state="readonly")
        self.device_combo.grid(row=0, column=1, sticky="we", **pad)
        self.device_combo.bind("<<ComboboxSelected>>", lambda e: self._save_device())
        ttk.Button(frame, text="🔄 Cihazları Yenile", command=self._refresh_devices).grid(
            row=0, column=2, sticky="w", **pad)

        ttk.Label(frame, text="Çalınacak zil sesi:").grid(row=1, column=0, sticky="w", **pad)
        self.default_sound_var = tk.StringVar(
            value=self.cfg.get("default_sound") or "(Seçilmedi - lütfen bir ses dosyası seçin)")
        ttk.Entry(frame, textvariable=self.default_sound_var, width=40, state="readonly").grid(
            row=1, column=1, sticky="we", **pad)
        ttk.Button(frame, text="📁 Seç...", command=self._choose_default_sound).grid(
            row=1, column=2, sticky="w", **pad)
        ttk.Button(frame, text="❌ Kaldır", command=self._clear_default_sound).grid(
            row=1, column=3, sticky="w", **pad)

        ttk.Label(frame, text="Ses seviyesi:").grid(row=2, column=0, sticky="w", **pad)
        self.volume_var = tk.DoubleVar(value=self.cfg.get("volume", 1.0) * 100)
        volume_scale = ttk.Scale(frame, from_=0, to=100, variable=self.volume_var,
                                  orient="horizontal", command=lambda v: self._save_volume())
        volume_scale.grid(row=2, column=1, sticky="we", **pad)

        ttk.Button(frame, text="🔊 Test Sesi Çal", style="Accent.TButton",
                   command=self._test_default_sound).grid(row=3, column=1, sticky="w", **pad)

        ttk.Separator(frame, orient="horizontal").grid(
            row=4, column=0, columnspan=3, sticky="we", padx=10, pady=10)

        ttk.Label(frame, text="🔥 Yangın butonu sesi:").grid(row=5, column=0, sticky="w", **pad)
        self.fire_button_sound_var = tk.StringVar(
            value=self.cfg.get("fire_button_sound")
            or "(Seçilmedi - varsayılan zil sesi çalınır)")
        ttk.Entry(frame, textvariable=self.fire_button_sound_var, width=40, state="readonly").grid(
            row=5, column=1, sticky="we", **pad)
        ttk.Button(frame, text="📁 Seç...", command=self._choose_fire_button_sound).grid(
            row=5, column=2, sticky="w", **pad)
        ttk.Button(frame, text="❌ Kaldır", command=self._clear_fire_button_sound).grid(
            row=5, column=3, sticky="w", **pad)

        frame.columnconfigure(1, weight=1)

    def _choose_fire_button_sound(self) -> None:
        path = filedialog.askopenfilename(
            title="Yangın butonu için ses dosyası seç",
            filetypes=[("Ses dosyaları", "*.wav *.mp3 *.ogg *.flac"), ("Tüm dosyalar", "*.*")])
        if path:
            self.fire_button_sound_var.set(path)
            self.cfg["fire_button_sound"] = path
            self._persist()

    def _clear_fire_button_sound(self) -> None:
        self.fire_button_sound_var.set("(Seçilmedi - varsayılan zil sesi çalınır)")
        self.cfg["fire_button_sound"] = None
        self._persist()

    # ---------- Ayarları dışa/içe aktarma (kod ile, eşleştirme gibi) ----------
    def _export_config(self) -> None:
        ExportCodeDialog(self, self.remote_control, self.cfg)

    def _import_config(self) -> None:
        dialog = ImportCodeDialog(self, self.remote_control)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        host_name, config = dialog.result
        if not messagebox.askyesno(
                APP_TITLE,
                f"'{host_name}' cihazından alınan ayarlar, mevcut TÜM ayarların (zil "
                "kayıtları, namaz vakitleri, tatil günleri, sesler) üzerine yazacak. "
                "Devam edilsin mi?"):
            return
        self.cfg = complete_config(config)
        self._persist()
        self._rebuild_all_tabs()
        self._log(f"Ayarlar '{host_name}' cihazından içe aktarıldı.")

    def _build_general_tab(self) -> None:
        frame = self.general_tab

        self.tray_var = tk.BooleanVar(value=self.cfg.get("minimize_to_tray", True))
        tray_check = ttk.Checkbutton(
            frame, text="Pencereyi kapatınca sistem tepsisine küçült (programı tamamen kapatma)",
            variable=self.tray_var, command=self._save_tray_setting)
        tray_check.pack(anchor="w", padx=10, pady=(12, 4))
        if tray_icon is None:
            tray_check.state(["disabled"])
            ttk.Label(frame, text="(Bu özellik için gerekli kütüphane bulunamadı)",
                      foreground="#666666").pack(anchor="w", padx=30)

        autostart_row = ttk.Frame(frame)
        autostart_row.pack(anchor="w", padx=10, pady=4, fill="x")
        self.autostart_var = tk.BooleanVar(
            value=autostart.is_enabled() if autostart.is_supported()
            else self.cfg.get("start_with_windows", False))
        autostart_check = ttk.Checkbutton(
            autostart_row, text="Windows açılışında otomatik başlat ve kapanırsa kendini "
                                 "yeniden aç",
            variable=self.autostart_var, command=self._save_autostart_setting)
        autostart_check.pack(side="left")
        if not autostart.is_supported():
            autostart_check.state(["disabled"])
            ttk.Label(autostart_row, text="(Sadece Windows'ta kullanılabilir)",
                      foreground="#666666").pack(side="left", padx=8)
        ttk.Label(
            frame, text="Açıksa: bilgisayar açıldığında program otomatik başlar VE bilgisayar "
                        "çalışır durumdayken program herhangi bir sebeple kapanırsa (çökme, "
                        "yanlışlıkla kapatma vb.) en geç 1 dakika içinde kendini yeniden açar. "
                        "Bilgisayarın kendisi kapatılırsa/fişi çekilirse bu tabii ki geçerli "
                        "değildir - bilgisayar tekrar açıldığında program yine otomatik başlar.",
            foreground="#666666", wraplength=820, justify="left").pack(
            anchor="w", padx=30, pady=(2, 0))

        log_row = ttk.Frame(frame)
        log_row.pack(anchor="w", padx=10, pady=(4, 12), fill="x")
        ttk.Label(log_row, text="Zil kayıtları ayrıca dosyaya da yazılır.").pack(side="left")
        ttk.Button(log_row, text="📁 Log Klasörünü Aç", command=self._open_log_folder).pack(
            side="left", padx=8)

        backup_frame = ttk.LabelFrame(frame, text="Ayarları Kod ile Aktar")
        backup_frame.pack(fill="x", padx=10, pady=(0, 8))
        backup_btn_frame = ttk.Frame(backup_frame)
        backup_btn_frame.pack(fill="x", padx=8, pady=8)
        ttk.Button(backup_btn_frame, text="🔑 Kod Oluştur (Dışa Aktar)",
                   command=self._export_config).pack(side="left", padx=4)
        ttk.Button(backup_btn_frame, text="📥 Kod ile İçe Aktar",
                   command=self._import_config).pack(side="left", padx=4)

        holidays_frame = ttk.LabelFrame(
            frame, text="Tatil Günleri (normal program bu tarihlerde çalmaz)")
        holidays_frame.pack(fill="both", expand=True, padx=10, pady=8)

        columns = ("date", "label", "ring")
        self.holidays_tree = ttk.Treeview(holidays_frame, columns=columns, show="headings",
                                           height=8)
        self.holidays_tree.heading("date", text="Tarih")
        self.holidays_tree.heading("label", text="Açıklama")
        self.holidays_tree.heading("ring", text="Özel Zil")
        self.holidays_tree.column("date", width=110, anchor="w")
        self.holidays_tree.column("label", width=300, anchor="w")
        self.holidays_tree.column("ring", width=180, anchor="w")
        self.holidays_tree.tag_configure("oddrow", background=ROW_ODD)
        self.holidays_tree.tag_configure("evenrow", background=ROW_EVEN)
        self.holidays_tree.pack(fill="both", expand=True, padx=8, pady=8)
        self.holidays_tree.bind("<Double-1>", lambda e: self._edit_holiday())

        btn_frame = ttk.Frame(holidays_frame)
        btn_frame.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btn_frame, text="➕ Ekle", style="Accent.TButton",
                   command=self._add_holiday).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="✏️ Düzenle", command=self._edit_holiday).pack(
            side="left", padx=4)
        ttk.Button(btn_frame, text="🗑️ Sil", command=self._delete_holiday).pack(side="left", padx=4)

    # ---------- Uzaktan erişim sekmesi ----------
    def _build_remote_tab(self) -> None:
        frame = self.remote_tab
        pad = {"padx": 10, "pady": 6}

        host_frame = ttk.LabelFrame(frame, text="Bu Cihazı Eşleştir (başka bir cihaz buna bağlansın)")
        host_frame.pack(fill="x", padx=10, pady=8)
        ttk.Label(
            host_frame,
            text="Bir eşleştirme kodu oluşturun ve karşı cihaza girin. Onayladığınızda "
                 "karşı cihaz zili uzaktan çaldırabilir/durdurabilir ve tüm ayarları "
                 "görüntüleyip değiştirebilir. Yalnızca aynı yerel ağda (WiFi/LAN) çalışır.",
            wraplength=760, justify="left").pack(anchor="w", **pad)
        ttk.Button(host_frame, text="🔑 Eşleştirme Kodu Oluştur", style="Accent.TButton",
                   command=self._generate_pairing_code).pack(anchor="w", **pad)
        # Kod 5-20 hane olabildiğinden, buton ile aynı satıra sığdırmaya
        # çalışmak (eski tasarım) uzun kodların kesilmesine/görünmemesine
        # yol açıyordu - kendi geniş satırında, salt-okunur ama seçilip
        # kopyalanabilir bir Entry olarak gösteriliyor.
        code_row = ttk.Frame(host_frame)
        code_row.pack(anchor="w", fill="x", **pad)
        self.pairing_code_var = tk.StringVar(value="")
        self.pairing_code_entry_display = ttk.Entry(
            code_row, textvariable=self.pairing_code_var, font=("Consolas", 20, "bold"),
            width=24, justify="left")
        self.pairing_code_entry_display.pack(side="left", fill="x", expand=True)
        ttk.Button(code_row, text="📋 Kopyala", command=self._copy_pairing_code).pack(
            side="left", padx=(8, 0))
        self.pairing_code_hint_var = tk.StringVar(value="")
        ttk.Label(host_frame, textvariable=self.pairing_code_hint_var,
                  foreground="#666666").pack(anchor="w", padx=10, pady=(0, 8))

        connect_frame = ttk.LabelFrame(frame, text="Başka Bir Cihaza Bağlan (kod ile)")
        connect_frame.pack(fill="x", padx=10, pady=8)
        connect_row = ttk.Frame(connect_frame)
        connect_row.pack(anchor="w", fill="x", **pad)
        ttk.Label(connect_row, text="Kod:").pack(side="left")
        self.pairing_code_entry_var = tk.StringVar(value="")
        ttk.Entry(connect_row, textvariable=self.pairing_code_entry_var, width=24).pack(
            side="left", padx=8)
        ttk.Button(connect_row, text="🔗 Bağlan", style="Accent.TButton",
                   command=self._connect_with_code).pack(side="left")
        self.pairing_status_var = tk.StringVar(value="")
        ttk.Label(connect_frame, textvariable=self.pairing_status_var,
                  foreground="#666666").pack(anchor="w", padx=10, pady=(0, 8))

        devices_frame = ttk.LabelFrame(frame, text="Eşleşmiş Cihazlar")
        devices_frame.pack(fill="both", expand=True, padx=10, pady=8)
        self.paired_tree = ttk.Treeview(devices_frame, columns=("name",), show="headings",
                                         height=6)
        self.paired_tree.heading("name", text="Cihaz")
        self.paired_tree.column("name", width=300, anchor="w")
        self.paired_tree.tag_configure("oddrow", background=ROW_ODD)
        self.paired_tree.tag_configure("evenrow", background=ROW_EVEN)
        self.paired_tree.pack(fill="both", expand=True, padx=8, pady=8)

        pdev_btn_frame = ttk.Frame(devices_frame)
        pdev_btn_frame.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(pdev_btn_frame, text="🔔 Zili Çal", command=self._remote_ring_selected).pack(
            side="left", padx=4)
        ttk.Button(pdev_btn_frame, text="🔥 Yangın Butonu",
                   command=self._remote_fire_button_selected).pack(side="left", padx=4)
        ttk.Button(pdev_btn_frame, text="⏹ Durdur", command=self._remote_stop_selected).pack(
            side="left", padx=4)
        ttk.Button(pdev_btn_frame, text="⚙️ Ayarları Görüntüle/Değiştir",
                   command=self._remote_edit_settings_selected).pack(side="left", padx=4)
        ttk.Button(pdev_btn_frame, text="🗑️ Eşleştirmeyi Kaldır",
                   command=self._remote_remove_selected).pack(side="left", padx=4)

        self._refresh_paired_devices_tree()

    def _refresh_paired_devices_tree(self) -> None:
        self.paired_tree.delete(*self.paired_tree.get_children())
        for i, peer in enumerate(self.remote_control.paired_devices):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            self.paired_tree.insert("", "end", iid=peer.peer_id, tags=(tag,), values=(peer.name,))

    def _selected_peer(self) -> Optional["remote_control.PairedDevice"]:
        selection = self.paired_tree.selection()
        if not selection:
            messagebox.showinfo(APP_TITLE, "Lütfen bir cihaz seçin.")
            return None
        peer_id = selection[0]
        return next((p for p in self.remote_control.paired_devices if p.peer_id == peer_id), None)

    def _generate_pairing_code(self) -> None:
        code = self.remote_control.generate_code()
        self.pairing_code_entry_display.configure(state="normal")
        self.pairing_code_var.set(code)
        self.pairing_code_entry_display.configure(state="readonly")
        self.pairing_code_hint_var.set(
            "5 dakika içinde girilmezse ya da bir kez kullanılınca bu kod geçersiz olur "
            "- yeni bir kod için tekrar oluşturun.")

    def _copy_pairing_code(self) -> None:
        code = self.pairing_code_var.get()
        if not code:
            return
        self.clipboard_clear()
        self.clipboard_append(code)

    def _connect_with_code(self) -> None:
        code = self.pairing_code_entry_var.get().strip()
        if not code:
            messagebox.showinfo(APP_TITLE, "Lütfen karşı cihazda gösterilen kodu girin.")
            return
        self.pairing_status_var.set("Aranıyor...")

        def worker():
            def status(text: str) -> None:
                try:
                    self.after(0, lambda: self.pairing_status_var.set(text))
                except RuntimeError:
                    pass
            peer = self.remote_control.pair_with_code(code, status)
            if peer is not None:
                try:
                    self.after(0, self._refresh_paired_devices_tree)
                except RuntimeError:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    def _remote_ring_selected(self) -> None:
        peer = self._selected_peer()
        if peer is None:
            return
        self._run_remote_command(peer, {"cmd": "ring_now", "sound": None},
                                  success_message="Uzak cihazda zil çaldırıldı.")

    def _remote_fire_button_selected(self) -> None:
        peer = self._selected_peer()
        if peer is None:
            return
        self._run_remote_command(peer, {"cmd": "fire_button"},
                                  success_message="Uzak cihazda yangın butonu tetiklendi.")

    def _remote_stop_selected(self) -> None:
        peer = self._selected_peer()
        if peer is None:
            return
        self._run_remote_command(peer, {"cmd": "stop"}, success_message="Uzak cihazda durduruldu.")

    def _remote_remove_selected(self) -> None:
        peer = self._selected_peer()
        if peer is None:
            return
        if not messagebox.askyesno(APP_TITLE, f"'{peer.name}' eşleştirmesi kaldırılsın mı?"):
            return
        self.remote_control.remove_paired_device(peer.peer_id)
        self._refresh_paired_devices_tree()

    def _remote_edit_settings_selected(self) -> None:
        peer = self._selected_peer()
        if peer is None:
            return

        def worker():
            try:
                result = self.remote_control.send_command(peer, {"cmd": "get_config"})
            except Exception as exc:
                self._log(f"Uzak ayarlar alınamadı: {exc}")
                try:
                    self.after(0, lambda: messagebox.showerror(
                        APP_TITLE, f"'{peer.name}' cihazına bağlanılamadı: {exc}"))
                except RuntimeError:
                    pass
                return
            if not result.get("ok"):
                return
            # Uzak cihaz eksik/kısmi bir config göndermiş olabilir (ör.
            # eski/farklı bir sürüm) - complete_config() ile tamamlanmazsa
            # sekmeler kurulurken KeyError ile çöker.
            remote_cfg = complete_config(dict(result.get("data") or {}))
            try:
                self.after(0, lambda: RemoteSettingsWindow(self, peer, remote_cfg,
                                                             self.remote_control, self._log))
            except RuntimeError:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _run_remote_command(self, peer: "remote_control.PairedDevice", cmd: dict,
                             success_message: str) -> None:
        def worker():
            try:
                result = self.remote_control.send_command(peer, cmd)
            except Exception as exc:
                self._log(f"'{peer.name}' cihazına ulaşılamadı: {exc}")
                return
            if result.get("ok"):
                self._log(success_message)
            else:
                self._log(f"'{peer.name}' komutu reddetti: {result.get('error')}")

        threading.Thread(target=worker, daemon=True).start()

    # ---------- Uzaktan erişim: gelen istekler/komutlar ----------
    def _on_remote_pairing_request(self, requester_name: str,
                                    decide: Callable[[bool], None]) -> None:
        def ask() -> None:
            dialog = PairingApprovalDialog(self, requester_name)
            self.wait_window(dialog)
            decide(dialog.result)
        try:
            self.after(0, ask)
        except RuntimeError:
            decide(False)

    def _remote_ring_now(self, sound: Optional[str]) -> None:
        try:
            audio_player.play_file(sound, self.cfg.get("output_device"),
                                    self.cfg.get("default_sound"), self.cfg.get("volume", 1.0))
        except Exception as exc:
            self._log(f"Uzaktan zil çalınamadı: {exc}")

    def _apply_remote_config(self, new_cfg: dict) -> None:
        def do_apply() -> None:
            from config_store import default_config
            merged = default_config()
            merged.update(new_cfg)
            # complete_config(), uzak taraf eksik/kısmi bir ayar gönderse
            # bile (ör. elle düzenlenmiş JSON) her alanın var olduğunu
            # garanti eder - aksi halde sekmeler yeniden kurulurken çöker.
            self.cfg = complete_config(merged)
            save_config(self.cfg)
            self._rebuild_all_tabs()
            self._log("Ayarlar uzaktan güncellendi.")
        try:
            self.after(0, do_apply)
        except RuntimeError:
            pass

    def _rebuild_all_tabs(self) -> None:
        for tab in (self.entries_tab, self.prayer_tab, self.audio_tab, self.general_tab,
                    self.remote_tab):
            for child in tab.winfo_children():
                child.destroy()
        self._build_entries_tab()
        self._build_prayer_tab()
        self._build_audio_tab()
        self._build_general_tab()
        self._build_remote_tab()
        self._refresh_entries_tree()
        self._refresh_friday_tree()
        self._refresh_devices()
        self._refresh_holidays_tree()

    def _save_paired_devices(self) -> None:
        save_paired_devices_raw([p.to_json() for p in self.remote_control.paired_devices])

        def refresh() -> None:
            if hasattr(self, "paired_tree"):
                self._refresh_paired_devices_tree()
        try:
            self.after(0, refresh)
        except RuntimeError:
            pass

    # ---------- Yardımcı: log ----------
    def _log(self, message: str) -> None:
        self._file_logger.info(message)

        def append():
            timestamp = datetime.now().strftime("%H:%M:%S")
            if message.startswith("Zil çalıyor"):
                tag = "ring"
            elif "hata" in message.lower() or "alınamadı" in message.lower():
                tag = "error"
            else:
                tag = "info"
            self.log_text.configure(state="normal")
            self.log_text.insert("end", f"[{timestamp}] {message}\n", tag)
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        try:
            self.after(0, append)
        except RuntimeError:
            pass  # pencere kapanmışsa yok say

    def _persist(self) -> None:
        save_config(self.cfg)

    # ---------- Zil programı sekmesi ----------
    def _refresh_entries_tree(self) -> None:
        self.entries_tree.delete(*self.entries_tree.get_children())
        for i, entry in enumerate(self.cfg["entries"]):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            self.entries_tree.insert("", "end", iid=entry["id"], tags=(tag,), values=(
                "Evet" if entry.get("enabled", True) else "Hayır",
                entry.get("label", ""),
                entry.get("time", ""),
                format_days(entry.get("days", [])),
                format_sound(entry.get("sound")),
            ))

    def _add_entry(self) -> None:
        dialog = EntryDialog(self)
        self.wait_window(dialog)
        if dialog.result:
            self.cfg["entries"].append(dialog.result)
            self._persist()
            self._refresh_entries_tree()

    def _selected_entry_id(self) -> Optional[str]:
        selection = self.entries_tree.selection()
        return selection[0] if selection else None

    def _edit_entry(self) -> None:
        entry_id = self._selected_entry_id()
        if not entry_id:
            messagebox.showinfo(APP_TITLE, "Lütfen düzenlemek için bir kayıt seçin.")
            return
        entry = next((e for e in self.cfg["entries"] if e["id"] == entry_id), None)
        if not entry:
            return
        dialog = EntryDialog(self, entry)
        self.wait_window(dialog)
        if dialog.result:
            idx = self.cfg["entries"].index(entry)
            self.cfg["entries"][idx] = dialog.result
            self._persist()
            self._refresh_entries_tree()

    def _delete_entry(self) -> None:
        entry_id = self._selected_entry_id()
        if not entry_id:
            messagebox.showinfo(APP_TITLE, "Lütfen silmek için bir kayıt seçin.")
            return
        if not messagebox.askyesno(APP_TITLE, "Seçili kayıt silinsin mi?"):
            return
        self.cfg["entries"] = [e for e in self.cfg["entries"] if e["id"] != entry_id]
        self._persist()
        self._refresh_entries_tree()

    def _test_entry(self) -> None:
        entry_id = self._selected_entry_id()
        entry = next((e for e in self.cfg["entries"] if e["id"] == entry_id), None)
        sound = entry.get("sound") if entry else "default"
        self._play_test_sound(sound)

    # ---------- Namaz vakitleri sekmesi ----------
    def _save_daily_setting(self, vakit: str) -> None:
        pair = self.daily_vars[vakit]
        self.cfg["prayer_times"]["daily"][vakit] = {
            "enabled": pair["enabled"].get(),
            "sound": pair["sound"].get().strip() or None,
        }
        self._persist()

    def _choose_daily_sound(self, vakit: str) -> None:
        path = filedialog.askopenfilename(
            title="Ses dosyası seç",
            filetypes=[("Ses dosyaları", "*.wav *.mp3 *.ogg *.flac"), ("Tüm dosyalar", "*.*")])
        if not path:
            return
        self.daily_vars[vakit]["sound"].set(path)
        self._save_daily_setting(vakit)

    def _clear_daily_sound(self, vakit: str) -> None:
        self.daily_vars[vakit]["sound"].set("")
        self._save_daily_setting(vakit)

    def _test_daily_sound(self, vakit: str) -> None:
        sound = self.daily_vars[vakit]["sound"].get().strip() or "default"
        self._play_test_sound(sound)

    def _refresh_friday_tree(self) -> None:
        self.friday_tree.delete(*self.friday_tree.get_children())
        for i, offset in enumerate(self.cfg["prayer_times"]["friday_offsets"]):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            self.friday_tree.insert("", "end", iid=offset["id"], tags=(tag,), values=(
                "Evet" if offset.get("enabled", True) else "Hayır",
                "Önce" if offset.get("direction", "before") == "before" else "Sonra",
                offset.get("minutes", 0),
                offset.get("label", ""),
                format_sound(offset.get("sound")),
            ))

    def _selected_friday_offset_id(self) -> Optional[str]:
        selection = self.friday_tree.selection()
        return selection[0] if selection else None

    def _add_friday_offset(self) -> None:
        dialog = FridayOffsetDialog(self)
        self.wait_window(dialog)
        if dialog.result:
            self.cfg["prayer_times"]["friday_offsets"].append(dialog.result)
            self._persist()
            self._refresh_friday_tree()

    def _edit_friday_offset(self) -> None:
        offset_id = self._selected_friday_offset_id()
        if not offset_id:
            messagebox.showinfo(APP_TITLE, "Lütfen düzenlemek için bir kayıt seçin.")
            return
        offset = next((o for o in self.cfg["prayer_times"]["friday_offsets"]
                       if o["id"] == offset_id), None)
        if not offset:
            return
        dialog = FridayOffsetDialog(self, offset)
        self.wait_window(dialog)
        if dialog.result:
            idx = self.cfg["prayer_times"]["friday_offsets"].index(offset)
            self.cfg["prayer_times"]["friday_offsets"][idx] = dialog.result
            self._persist()
            self._refresh_friday_tree()

    def _delete_friday_offset(self) -> None:
        offset_id = self._selected_friday_offset_id()
        if not offset_id:
            messagebox.showinfo(APP_TITLE, "Lütfen silmek için bir kayıt seçin.")
            return
        if not messagebox.askyesno(APP_TITLE, "Seçili kayıt silinsin mi?"):
            return
        self.cfg["prayer_times"]["friday_offsets"] = [
            o for o in self.cfg["prayer_times"]["friday_offsets"] if o["id"] != offset_id]
        self._persist()
        self._refresh_friday_tree()

    def _test_friday_offset(self) -> None:
        offset_id = self._selected_friday_offset_id()
        offset = next((o for o in self.cfg["prayer_times"]["friday_offsets"]
                       if o["id"] == offset_id), None)
        if not offset:
            messagebox.showinfo(APP_TITLE, "Lütfen test etmek için bir kayıt seçin.")
            return
        self._play_test_sound(offset.get("sound") or "default")

    def _save_prayer_general_settings(self) -> None:
        pt = self.cfg["prayer_times"]
        pt["enabled"] = self.prayer_enabled_var.get()
        pt["city"] = self.prayer_city_var.get().strip()
        pt["en_ustte_goster"] = self.prayer_topmost_var.get()
        self.attributes("-topmost", pt["en_ustte_goster"])
        self._persist()

    def _manual_save_prayer_settings(self) -> None:
        self._save_prayer_general_settings()
        messagebox.showinfo(APP_TITLE, "Namaz vakti ayarları kaydedildi.")

    def _show_today_prayer_times(self) -> None:
        city = self.prayer_city_var.get().strip()
        if not city:
            messagebox.showinfo(APP_TITLE, "Lütfen önce il/ilçe girin.")
            return
        self.prayer_info_var.set("Sorgulanıyor...")
        self.update_idletasks()
        timings, from_network = prayer_service.get_cached_or_fetch_day(
            city, target_date=date.today())
        if not timings:
            self.prayer_info_var.set("Vakitler alınamadı. İnternet bağlantınızı kontrol edin.")
            return
        parts = [f"{prayer_service.VAKIT_LABELS[v]}: {timings[v]}"
                 for v in VAKIT_KEYS if v in timings]
        self.prayer_info_var.set("  |  ".join(parts))

    # ---------- Ses ayarları sekmesi ----------
    def _refresh_devices(self) -> None:
        devices = audio_player.list_output_devices()
        names = [d.name for d in devices]
        self.device_combo["values"] = ["(Sistem Varsayılanı)"] + names
        current = self.cfg.get("output_device")
        if current and current in names:
            self.device_var.set(current)
        else:
            self.device_var.set("(Sistem Varsayılanı)")

    def _save_device(self) -> None:
        value = self.device_var.get()
        self.cfg["output_device"] = None if value == "(Sistem Varsayılanı)" else value
        self._persist()

    def _choose_default_sound(self) -> None:
        path = filedialog.askopenfilename(
            title="Varsayılan ses dosyası seç",
            filetypes=[("Ses dosyaları", "*.wav *.mp3 *.ogg *.flac"), ("Tüm dosyalar", "*.*")])
        if path:
            self.default_sound_var.set(path)
            self.cfg["default_sound"] = path
            self._persist()

    def _clear_default_sound(self) -> None:
        self.default_sound_var.set("(Seçilmedi - lütfen bir ses dosyası seçin)")
        self.cfg["default_sound"] = None
        self._persist()

    def _save_volume(self) -> None:
        self.cfg["volume"] = self.volume_var.get() / 100.0
        self._persist()

    def _test_default_sound(self) -> None:
        self._play_test_sound(self.cfg.get("default_sound", "default"))

    def _play_test_sound(self, sound: Optional[str]) -> None:
        try:
            audio_player.play_file(sound, self.cfg.get("output_device"),
                                    self.cfg.get("default_sound"), self.cfg.get("volume", 1.0))
            self._log("Test sesi çalındı.")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Ses çalınamadı: {exc}")

    # ---------- Genel sekmesi: sistem tepsisi ----------
    def _start_tray(self) -> None:
        if tray_icon is None or self._tray is not None:
            return
        try:
            self._tray = tray_icon.TrayIcon()
            self._tray.start()
            self.after(200, self._poll_tray_queue)
        except Exception as exc:
            self._log(f"Sistem tepsisi simgesi başlatılamadı: {exc}")
            self._tray = None

    def _stop_tray(self) -> None:
        if self._tray is not None:
            self._tray.stop()
            self._tray = None

    def _poll_tray_queue(self) -> None:
        if self._tray is None:
            return
        try:
            while True:
                cmd = self._tray.commands.get_nowait()
                if cmd == tray_icon.SHOW:
                    self._show_window()
                elif cmd == tray_icon.QUIT:
                    self._quit_app()
                    return
        except queue.Empty:
            pass
        self.after(200, self._poll_tray_queue)

    def _show_window(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    # ---------- Genel: tekil örnek (exe tekrar açılırsa) ----------
    def _poll_instance_queue(self) -> None:
        if self._instance is None:
            return
        try:
            while True:
                self._instance.show_requests.get_nowait()
                self._show_window()
        except queue.Empty:
            pass
        self.after(200, self._poll_instance_queue)

    def _save_tray_setting(self) -> None:
        self.cfg["minimize_to_tray"] = self.tray_var.get()
        self._persist()
        if self.tray_var.get():
            self._start_tray()
        else:
            self._stop_tray()

    # ---------- Genel sekmesi: otomatik başlatma ----------
    def _save_autostart_setting(self) -> None:
        enabled = self.autostart_var.get()
        try:
            autostart.set_enabled(enabled)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Otomatik başlatma ayarlanamadı: {exc}")
            self.autostart_var.set(not enabled)
            return
        self.cfg["start_with_windows"] = enabled
        self._persist()

    # ---------- Genel sekmesi: log klasörü ----------
    def _open_log_folder(self) -> None:
        log_dir = app_logging.get_log_dir()
        try:
            if sys.platform == "win32":
                os.startfile(log_dir)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", str(log_dir)], check=False)
            else:
                subprocess.run(["xdg-open", str(log_dir)], check=False)
        except Exception as exc:
            messagebox.showinfo(APP_TITLE, f"Log klasörü: {log_dir}\n(Otomatik açılamadı: {exc})")

    # ---------- Genel sekmesi: tatil günleri ----------
    def _refresh_holidays_tree(self) -> None:
        self.holidays_tree.delete(*self.holidays_tree.get_children())
        holidays = sorted(self.cfg.get("holidays", []), key=lambda h: h.get("date", ""))
        for i, holiday in enumerate(holidays):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            ring_text = f"{holiday.get('ring_time')} - {format_sound(holiday.get('ring_sound'))}" \
                if holiday.get("ring") else "(Zil çalmaz)"
            self.holidays_tree.insert("", "end", iid=holiday["date"], tags=(tag,), values=(
                format_holiday_date(holiday.get("date", "")), holiday.get("label", ""), ring_text))

    def _add_holiday(self) -> None:
        dialog = HolidayDialog(self)
        self.wait_window(dialog)
        if dialog.result:
            self.cfg.setdefault("holidays", [])
            self.cfg["holidays"] = [h for h in self.cfg["holidays"]
                                     if h["date"] != dialog.result["date"]]
            self.cfg["holidays"].append(dialog.result)
            self._persist()
            self._refresh_holidays_tree()

    def _edit_holiday(self) -> None:
        selection = self.holidays_tree.selection()
        if not selection:
            messagebox.showinfo(APP_TITLE, "Lütfen düzenlemek için bir tarih seçin.")
            return
        date_iso = selection[0]
        holiday = next((h for h in self.cfg.get("holidays", []) if h["date"] == date_iso), None)
        if holiday is None:
            return
        dialog = HolidayDialog(self, holiday=holiday)
        self.wait_window(dialog)
        if dialog.result:
            self.cfg["holidays"] = [h for h in self.cfg["holidays"] if h["date"] != date_iso]
            self.cfg["holidays"].append(dialog.result)
            self._persist()
            self._refresh_holidays_tree()

    def _delete_holiday(self) -> None:
        selection = self.holidays_tree.selection()
        if not selection:
            messagebox.showinfo(APP_TITLE, "Lütfen silmek için bir tarih seçin.")
            return
        if not messagebox.askyesno(APP_TITLE, "Seçili tatil günü silinsin mi?"):
            return
        date_iso = selection[0]
        self.cfg["holidays"] = [h for h in self.cfg["holidays"] if h["date"] != date_iso]
        self._persist()
        self._refresh_holidays_tree()

    # ---------- Kapanış ----------
    def _on_close(self) -> None:
        if self.cfg.get("minimize_to_tray", True) and self._tray is not None:
            self.withdraw()
            self._log("Pencere sistem tepsisine küçültüldü. Program arka planda çalışmaya devam ediyor.")
        else:
            self._quit_app()

    def _quit_app(self) -> None:
        self.scheduler.stop()
        self.remote_control.stop()
        self._stop_tray()
        self.destroy()
