"""Arka planda çalışan zamanlayıcı: düzenli zil saatlerini ve her Cuma için
otomatik hesaplanan Cuma namazı öncesi zil vakitlerini takip edip
tetikleyen thread."""
from __future__ import annotations

import threading
import time
from datetime import date, datetime
from typing import Callable, Optional

import audio_player
import prayer_service

CHECK_INTERVAL_SECONDS = 5


class BellScheduler(threading.Thread):
    def __init__(self, get_config: Callable[[], dict], on_log: Callable[[str], None]):
        super().__init__(daemon=True)
        self._get_config = get_config
        self._on_log = on_log
        self._stop_event = threading.Event()
        self._fired_today: set[str] = set()
        self._fired_date: Optional[date] = None
        self._friday_cache: dict[str, Optional[str]] = {}  # cache_key -> "HH:MM"
        self._friday_cache_date: Optional[date] = None

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

    def _tick(self) -> None:
        cfg = self._get_config()
        now = datetime.now()
        today = now.date()
        self._reset_daily_state_if_needed(today)
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

        if weekday == 4:  # Cuma
            self._check_friday_prayer(cfg, today, current_hhmm)

    def _check_friday_prayer(self, cfg: dict, today: date, current_hhmm: str) -> None:
        fp = cfg.get("friday_prayer", {})
        if not fp.get("enabled", False):
            return

        city = fp.get("city", "").strip()
        country = fp.get("country", "Turkey").strip() or "Turkey"
        if not city:
            return

        cache_key = f"{country}|{city}|{today.isoformat()}"
        if self._friday_cache_date != today:
            self._friday_cache.clear()
            self._friday_cache_date = today

        if cache_key not in self._friday_cache:
            dhuhr_time, from_network = prayer_service.get_cached_or_fetch(
                city, country, target_date=today)
            self._friday_cache[cache_key] = dhuhr_time
            if dhuhr_time:
                source = "internetten" if from_network else "önbellekten"
                self._on_log(f"{city} için Cuma namazı vakti {source} alındı: {dhuhr_time}")
            else:
                self._on_log(
                    f"{city} için Cuma namazı vakti alınamadı (internet bağlantısını kontrol edin).")

        dhuhr_time = self._friday_cache.get(cache_key)
        if not dhuhr_time:
            return

        for offset in fp.get("offsets", []):
            if not offset.get("enabled", True):
                continue
            minutes = offset.get("minutes", 0)
            direction = offset.get("direction", "before")
            target_hhmm = prayer_service.compute_relative_time(dhuhr_time, minutes, direction)
            if target_hhmm != current_hhmm:
                continue
            fire_key = f"friday:{direction}:{minutes}:{today.isoformat()}"
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
