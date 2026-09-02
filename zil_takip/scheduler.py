"""Arka planda çalışan zamanlayıcı: düzenli zil saatlerini ve her gün
otomatik hesaplanan namaz vakitlerini (+ sela, kerahat hatırlatması)
takip edip tetikleyen thread."""
from __future__ import annotations

import threading
from datetime import date, datetime
from typing import Callable, Optional

import audio_player
import prayer_service

CHECK_INTERVAL_SECONDS = 5


def _signed_offset(minutes: int, direction: str) -> int:
    """'before' vaktin öncesine (negatif), 'after' vaktin sonrasına
    (pozitif) kaydırır - ör. namazdan 30 dk sonra mesaiye dönüş zili."""
    return minutes if direction == "after" else -minutes


class BellScheduler(threading.Thread):
    def __init__(self, get_config: Callable[[], dict], on_log: Callable[[str], None],
                 on_visual: Optional[Callable[[str, str, Optional[Callable[[], None]]], None]] = None):
        super().__init__(daemon=True)
        self._get_config = get_config
        self._on_log = on_log
        # (baslik, altbaslik, on_dismiss) parametreleriyle cagrilir; ana
        # pencere bunu kendi thread'inde bir Toplevel olarak gosterir.
        self._on_visual = on_visual
        self._stop_event = threading.Event()
        self._fired_today: set[str] = set()
        self._fired_date: Optional[date] = None
        self._timings_cache: dict[str, dict[str, str]] = {}  # cache_key -> {"imsak": "HH:MM", ...}
        self._timings_cache_date: Optional[date] = None
        self._holiday_notice_shown = False

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as exc:  # zamanlayıcı asla tamamen durmamalı
                self._on_log(f"Zamanlayıcı hatası: {exc}")
            self._stop_event.wait(CHECK_INTERVAL_SECONDS)

    def _reset_daily_state_if_needed(self, today: date) -> None:
        if self._fired_date != today:
            self._fired_date = today
            self._fired_today.clear()
            self._holiday_notice_shown = False

    def _tick(self) -> None:
        cfg = self._get_config()
        now = datetime.now()
        today = now.date()
        self._reset_daily_state_if_needed(today)

        holiday = next((h for h in cfg.get("holidays", [])
                         if h.get("date") == today.isoformat()), None)
        if holiday is not None:
            if not self._holiday_notice_shown:
                self._holiday_notice_shown = True
                label = holiday.get("label") or "Tatil günü"
                self._on_log(f"Bugün tatil ({label}) - ziller çalmayacak.")
            return

        current_hhmm = now.strftime("%H:%M")
        weekday = now.weekday()  # Pazartesi=0 ... Pazar=6

        for entry in cfg.get("entries", []):
            if not entry.get("enabled", True):
                continue
            if weekday not in entry.get("days", []):
                continue
            if entry.get("time") != current_hhmm:
                continue
            fire_key = f"entry:{entry['id']}"
            if fire_key in self._fired_today:
                continue
            self._fired_today.add(fire_key)
            self._ring(entry.get("label", "Zil"), entry.get("sound"), cfg)

        self._check_prayer_times(cfg, today, current_hhmm, weekday)

    # ---------- Namaz vakitleri ----------
    def _get_today_timings(self, cfg: dict, today: date) -> Optional[dict[str, str]]:
        pt = cfg.get("prayer_times", {})
        city = pt.get("city", "").strip()
        country = pt.get("country", "Turkey").strip() or "Turkey"
        if not city:
            return None

        cache_key = f"{country}|{city}|{today.isoformat()}"
        if self._timings_cache_date != today:
            self._timings_cache.clear()
            self._timings_cache_date = today

        if cache_key not in self._timings_cache:
            timings, from_network = prayer_service.get_cached_or_fetch_day(
                city, country, target_date=today)
            self._timings_cache[cache_key] = timings
            if timings:
                source = "internetten" if from_network else "önbellekten"
                self._on_log(f"{city} için namaz vakitleri {source} alındı.")
            else:
                self._on_log(
                    f"{city} için namaz vakitleri alınamadı (internet bağlantısını kontrol edin).")

        return self._timings_cache.get(cache_key)

    def _check_prayer_times(self, cfg: dict, today: date, current_hhmm: str, weekday: int) -> None:
        pt = cfg.get("prayer_times", {})
        if not pt.get("enabled", False):
            return

        timings = self._get_today_timings(cfg, today)
        if not timings:
            return

        temkin = pt.get("temkin_suresi_dk", 0)
        is_friday = weekday == 4

        for alert in pt.get("alerts", []):
            if not alert.get("enabled", True):
                continue
            if alert.get("friday_only") and not is_friday:
                continue
            vakit = alert.get("vakit", "ogle")
            base_time = timings.get(vakit)
            if not base_time or not (alert.get("sesli") or alert.get("gorsel")):
                continue
            minutes = alert.get("minutes", 0)
            direction = alert.get("direction", "before")
            trigger_time = prayer_service.apply_offset_minutes(
                base_time, temkin + _signed_offset(minutes, direction))
            if trigger_time != current_hhmm:
                continue
            fire_key = f"alert:{alert.get('id')}:{today.isoformat()}"
            if fire_key in self._fired_today:
                continue
            self._fired_today.add(fire_key)
            label = alert.get("label") or self._default_alert_label(vakit, minutes, direction)
            self._fire_vakit(label, f"Vakit: {base_time}", alert, pt)

        if pt.get("kerahat_hatirlat"):
            self._check_kerahat(timings, today, current_hhmm)

    @staticmethod
    def _default_alert_label(vakit: str, minutes: int, direction: str) -> str:
        label = prayer_service.VAKIT_LABELS.get(vakit, vakit)
        if minutes:
            label += f" - {minutes} dk {'kala' if direction == 'before' else 'sonra'}"
        return label

    def _check_kerahat(self, timings: dict[str, str], today: date, current_hhmm: str) -> None:
        for label, start, _end in prayer_service.compute_kerahat_windows(timings):
            if start != current_hhmm:
                continue
            fire_key = f"kerahat:{label}:{today.isoformat()}"
            if fire_key in self._fired_today:
                continue
            self._fired_today.add(fire_key)
            self._on_log(f"Kerahat vakti başladı: {label}")
            if self._on_visual:
                self._on_visual(label, "Bu aralıkta namaz kılınması mekruh sayılır.", None)

    def _fire_vakit(self, label: str, subtitle: str, setting: dict, pt: dict) -> None:
        self._on_log(f"Vakit bildirimi: {label}")
        sesli = setting.get("sesli")
        gorsel = setting.get("gorsel")
        sound = setting.get("sound")

        def play_sound() -> None:
            self._play_sound(label, sound)

        if gorsel and self._on_visual:
            sequential = sesli and pt.get("gorsel_sonrasi_sesli")
            self._on_visual(label, subtitle, play_sound if sequential else None)
            if sesli and not sequential:
                play_sound()
        elif sesli:
            play_sound()

    def _play_sound(self, label: str, sound: Optional[str]) -> None:
        cfg = self._get_config()
        try:
            audio_player.play_file(sound, cfg.get("output_device"),
                                    cfg.get("default_sound"), cfg.get("volume", 1.0))
        except Exception as exc:
            self._on_log(f"Ses çalınamadı ({label}): {exc}")

    def _ring(self, label: str, sound: Optional[str], cfg: dict) -> None:
        self._on_log(f"Zil çalıyor: {label}")
        try:
            audio_player.play_file(sound, cfg.get("output_device"),
                                    cfg.get("default_sound"), cfg.get("volume", 1.0))
        except Exception as exc:
            self._on_log(f"Ses çalınamadı ({label}): {exc}")
