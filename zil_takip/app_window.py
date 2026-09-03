"""Ceselsan Zil Takip Programı - Ana pencere (Tkinter arayüzü)."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import tkinter as tk
import uuid
from datetime import date, datetime
from tkinter import filedialog, messagebox, ttk
from typing import Optional

import app_logging
import audio_player
import autostart
import prayer_service
from config_store import VAKIT_KEYS, load_config, save_config
from scheduler import BellScheduler

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
    """Tatil günü ekleme penceresi - bu tarihlerde hiçbir zil çalmaz."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Tatil Günü Ekle")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.result: Optional[dict] = None
        self.transient(parent)
        self.grab_set()

        self.date_var = tk.StringVar(value=datetime.now().strftime("%d.%m.%Y"))
        self.label_var = tk.StringVar(value="")

        pad = {"padx": 10, "pady": 6}
        ttk.Label(self, text="Tarih (GG.AA.YYYY):").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.date_var, width=14).grid(
            row=0, column=1, sticky="w", **pad)

        ttk.Label(self, text="Açıklama:").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.label_var, width=32).grid(
            row=1, column=1, sticky="we", **pad)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="💾 Kaydet", style="Accent.TButton",
                   command=self._on_save).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="İptal", command=self.destroy).pack(side="left", padx=6)

    def _on_save(self) -> None:
        date_str = self.date_var.get().strip()
        try:
            parsed = datetime.strptime(date_str, "%d.%m.%Y")
        except ValueError:
            messagebox.showerror(APP_TITLE, "Tarih GG.AA.YYYY formatında olmalıdır. Örnek: 23.04.2027")
            return
        self.result = {"date": parsed.strftime("%Y-%m-%d"), "label": self.label_var.get().strip()}
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("860x660")
        self.minsize(760, 560)
        self.configure(bg=BG)

        self._setup_style()

        self.cfg = load_config()
        self._file_logger = app_logging.get_logger()
        self._tray: Optional["tray_icon.TrayIcon"] = None

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
        notebook.add(self.entries_tab, text="🔔 Zil Programı")
        notebook.add(self.prayer_tab, text="🕌 Namaz Vakitleri")
        notebook.add(self.audio_tab, text="🔊 Ses Ayarları")
        notebook.add(self.general_tab, text="⚙️ Genel")

        self._build_entries_tab()
        self._build_prayer_tab()
        self._build_audio_tab()
        self._build_general_tab()

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
            ttk.Button(daily_frame, text="▶ Test", width=6,
                       command=lambda v=vakit: self._test_daily_sound(v)).grid(
                row=i, column=4, padx=(2, 8), pady=3)

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

        ttk.Label(frame, text="Ses seviyesi:").grid(row=2, column=0, sticky="w", **pad)
        self.volume_var = tk.DoubleVar(value=self.cfg.get("volume", 1.0) * 100)
        volume_scale = ttk.Scale(frame, from_=0, to=100, variable=self.volume_var,
                                  orient="horizontal", command=lambda v: self._save_volume())
        volume_scale.grid(row=2, column=1, sticky="we", **pad)

        ttk.Button(frame, text="🔊 Test Sesi Çal", style="Accent.TButton",
                   command=self._test_default_sound).grid(row=3, column=1, sticky="w", **pad)

        frame.columnconfigure(1, weight=1)

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
            autostart_row, text="Windows açılışında otomatik başlat",
            variable=self.autostart_var, command=self._save_autostart_setting)
        autostart_check.pack(side="left")
        if not autostart.is_supported():
            autostart_check.state(["disabled"])
            ttk.Label(autostart_row, text="(Sadece Windows'ta kullanılabilir)",
                      foreground="#666666").pack(side="left", padx=8)

        log_row = ttk.Frame(frame)
        log_row.pack(anchor="w", padx=10, pady=(4, 12), fill="x")
        ttk.Label(log_row, text="Zil kayıtları ayrıca dosyaya da yazılır.").pack(side="left")
        ttk.Button(log_row, text="📁 Log Klasörünü Aç", command=self._open_log_folder).pack(
            side="left", padx=8)

        holidays_frame = ttk.LabelFrame(frame, text="Tatil Günleri (bu tarihlerde hiç zil çalmaz)")
        holidays_frame.pack(fill="both", expand=True, padx=10, pady=8)

        columns = ("date", "label")
        self.holidays_tree = ttk.Treeview(holidays_frame, columns=columns, show="headings",
                                           height=8)
        self.holidays_tree.heading("date", text="Tarih")
        self.holidays_tree.heading("label", text="Açıklama")
        self.holidays_tree.column("date", width=110, anchor="w")
        self.holidays_tree.column("label", width=420, anchor="w")
        self.holidays_tree.tag_configure("oddrow", background=ROW_ODD)
        self.holidays_tree.tag_configure("evenrow", background=ROW_EVEN)
        self.holidays_tree.pack(fill="both", expand=True, padx=8, pady=8)

        btn_frame = ttk.Frame(holidays_frame)
        btn_frame.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btn_frame, text="➕ Ekle", style="Accent.TButton",
                   command=self._add_holiday).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="🗑️ Sil", command=self._delete_holiday).pack(side="left", padx=4)

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
                    self.deiconify()
                    self.lift()
                    self.focus_force()
                elif cmd == tray_icon.QUIT:
                    self._quit_app()
                    return
        except queue.Empty:
            pass
        self.after(200, self._poll_tray_queue)

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
            self.holidays_tree.insert("", "end", iid=holiday["date"], tags=(tag,), values=(
                format_holiday_date(holiday.get("date", "")), holiday.get("label", "")))

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
        self._stop_tray()
        self.destroy()
