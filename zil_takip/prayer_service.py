"""Seçilen il/ilçe için Cuma namazı (öğle) vaktini internetten çekip
önbellekleyen modül.

Diyanet İşleri Başkanlığı hesaplama yöntemiyle (method=13) Aladhan API
kullanılır: https://aladhan.com/prayer-times-api
Cuma namazı vakti, o günün öğle (Dhuhr) vaktiyle aynıdır.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

from config_store import get_app_data_dir

ALADHAN_URL = "https://api.aladhan.com/v1/timingsByCity"
DIYANET_METHOD = 13
REQUEST_TIMEOUT_SECONDS = 10
CACHE_FILE_NAME = "cuma_vakti_cache.json"


def _cache_path() -> Path:
    return get_app_data_dir() / CACHE_FILE_NAME


def _load_cache() -> dict:
    path = _cache_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict) -> None:
    try:
        with open(_cache_path(), "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def next_friday(from_date: Optional[date] = None) -> date:
    d = from_date or date.today()
    days_ahead = (4 - d.weekday()) % 7  # Cuma = weekday() 4
    return d + timedelta(days=days_ahead)


def fetch_dhuhr_time(target_date: date, city: str, country: str = "Turkey") -> Optional[str]:
    """Verilen tarih ve şehir için öğle vaktini "HH:MM" formatında döndürür.
    Başarısız olursa None döner."""
    params = {
        "city": city,
        "country": country,
        "method": DIYANET_METHOD,
        "date": target_date.strftime("%d-%m-%Y"),
    }
    response = requests.get(ALADHAN_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json()
    timings = payload["data"]["timings"]
    dhuhr = timings["Dhuhr"]
    # API bazen "13:12 (+03)" gibi bölge bilgisi ekleyebiliyor, sadece saat:dk alınır
    return dhuhr.split(" ")[0].strip()


def get_cached_or_fetch(city: str, country: str = "Turkey",
                         target_date: Optional[date] = None) -> tuple[Optional[str], bool]:
    """(saat_string, internetten_mi_alindi) döndürür. İnternet yoksa ve
    önbellekte aynı tarih/şehir için kayıt varsa onu döndürür."""
    target_date = target_date or next_friday()
    cache_key = f"{country}|{city}|{target_date.isoformat()}"
    cache = _load_cache()

    try:
        time_str = fetch_dhuhr_time(target_date, city, country)
        cache[cache_key] = time_str
        _save_cache(cache)
        return time_str, True
    except Exception:
        cached = cache.get(cache_key)
        return cached, False


def compute_offset_time(hhmm: str, minutes_before: int) -> str:
    """'13:12' - 30 dk => '12:42' gibi hesaplama yapar."""
    base = datetime.strptime(hhmm, "%H:%M")
    result = base - timedelta(minutes=minutes_before)
    return result.strftime("%H:%M")
