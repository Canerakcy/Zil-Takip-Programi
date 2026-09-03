"""Seçilen il/ilçe için günlük namaz vakitlerini internetten çekip
önbellekleyen modül.

Diyanet İşleri Başkanlığı hesaplama yöntemiyle (method=13) Aladhan API
kullanılır: https://aladhan.com/prayer-times-api
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
CACHE_FILE_NAME = "vakit_cache.json"

# Uygulama içindeki vakit anahtarları -> Aladhan API'deki timings alan adları.
VAKIT_TO_ALADHAN_KEY = {
    "imsak": "Imsak",
    "gunes": "Sunrise",
    "ogle": "Dhuhr",
    "ikindi": "Asr",
    "aksam": "Maghrib",
    "yatsi": "Isha",
}

VAKIT_LABELS = {
    "imsak": "İmsak",
    "gunes": "Güneş",
    "ogle": "Öğle",
    "ikindi": "İkindi",
    "aksam": "Akşam",
    "yatsi": "Yatsı",
}


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


def _clean_hhmm(value: str) -> str:
    # API bazen "13:12 (+03)" gibi bölge bilgisi ekleyebiliyor, sadece saat:dk alınır
    return value.split(" ")[0].strip()


def fetch_day_timings(target_date: date, city: str, country: str = "Turkey") -> dict[str, str]:
    """Verilen tarih/şehir için tüm vakitleri {"imsak": "HH:MM", ...}
    şeklinde döndürür. Başarısız olursa istisna fırlatır."""
    params = {
        "city": city,
        "country": country,
        "method": DIYANET_METHOD,
        "date": target_date.strftime("%d-%m-%Y"),
    }
    response = requests.get(ALADHAN_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    timings = response.json()["data"]["timings"]
    return {vakit: _clean_hhmm(timings[aladhan_key])
            for vakit, aladhan_key in VAKIT_TO_ALADHAN_KEY.items()}


def get_cached_or_fetch_day(city: str, country: str = "Turkey",
                             target_date: Optional[date] = None
                             ) -> tuple[Optional[dict[str, str]], bool]:
    """(vakitler_dict, internetten_mi_alindi) döndürür. İnternet yoksa ve
    önbellekte aynı tarih/şehir için kayıt varsa onu döndürür."""
    target_date = target_date or date.today()
    cache_key = f"{country}|{city}|{target_date.isoformat()}"
    cache = _load_cache()

    try:
        timings = fetch_day_timings(target_date, city, country)
        cache[cache_key] = timings
        _save_cache(cache)
        return timings, True
    except Exception:
        cached = cache.get(cache_key)
        return cached, False


def apply_offset_minutes(hhmm: str, minutes: int) -> str:
    """Bir vakte, işaretli (pozitif/negatif) dakika ekler - Cuma namazı
    önce/sonra kayıtları için kullanılır (bkz. scheduler.py > _signed_offset).
    Pozitif değer sonraya, negatif değer öncesine kaydırır."""
    base = datetime.strptime(hhmm, "%H:%M")
    result = base + timedelta(minutes=minutes)
    return result.strftime("%H:%M")
