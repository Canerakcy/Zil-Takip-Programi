"""Arka planda çalışan zamanlayıcı: düzenli zil saatlerini, günlük namaz
vakitlerini ve Cuma namazına özel önce/sonra kayıtlarını takip edip
tetikleyen thread."""
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
    def __init__(self, get_config: Callable[[], dict], on_log: Callable[[str], None]):
        super().__init__(daemon=True)
        self._get_config = get_config
        self._on_log = on_log
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

        # Günlük vakit sesi: her vakit tam kendi saatinde, açıksa seçilen
        # sesi çalar - dakika/yön hesabı yok.
        for vakit, setting in pt.get("daily", {}).items():
            if not setting.get("enabled"):
                continue
            base_time = timings.get(vakit)
            if not base_time or base_time != current_hhmm:
                continue
            fire_key = f"daily:{vakit}:{today.isoformat()}"
            if fire_key in self._fired_today:
                continue
            self._fired_today.add(fire_key)
            label = prayer_service.VAKIT_LABELS.get(vakit, vakit)
            self._ring(label, setting.get("sound"), cfg)

        # Cuma namazına özel önce/sonra kayıtları - sadece Cuma günleri,
        # öğle/Cuma vaktine göre hesaplanır.
        if weekday != 4:  # Cuma değilse hiç bakma
            return
        ogle = timings.get("ogle")
        if not ogle:
            return
        for offset in pt.get("friday_offsets", []):
            if not offset.get("enabled", True):
                continue
            minutes = offset.get("minutes", 0)
            direction = offset.get("direction", "before")
            trigger_time = prayer_service.apply_offset_minutes(
                ogle, _signed_offset(minutes, direction))
            if trigger_time != current_hhmm:
                continue
            fire_key = f"friday:{offset.get('id')}:{today.isoformat()}"
            if fire_key in self._fired_today:
                continue
            self._fired_today.add(fire_key)
            direction_text = "kala" if direction == "before" else "sonra"
            label = offset.get("label") or f"Cuma Namazı - {minutes} dk {direction_text}"
            self._ring(label, offset.get("sound"), cfg)

    def _ring(self, label: str, sound: Optional[str], cfg: dict) -> None:
        self._on_log(f"Zil çalıyor: {label}")
        try:
            audio_player.play_file(sound, cfg.get("output_device"),
                                    cfg.get("default_sound"), cfg.get("volume", 1.0))
        except Exception as exc:
            self._on_log(f"Ses çalınamadı ({label}): {exc}")
