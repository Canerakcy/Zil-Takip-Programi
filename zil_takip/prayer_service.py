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
# "gunes" (güneş doğuşu) ve "sela" ayrı tutulur; sela'nın kendi bir Aladhan
# karşılığı yoktur, öğle vaktine göre hesaplanır (bkz. scheduler.py).
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
    "sela": "Sela",
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


def next_friday(from_date: Optional[date] = None) -> date:
    d = from_date or date.today()
    days_ahead = (4 - d.weekday()) % 7  # Cuma = weekday() 4
    return d + timedelta(days=days_ahead)


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


def fetch_dhuhr_time(target_date: date, city: str, country: str = "Turkey") -> Optional[str]:
    """Geriye dönük uyumluluk için: sadece öğle vaktini döndürür."""
    return fetch_day_timings(target_date, city, country).get("ogle")


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


def get_cached_or_fetch(city: str, country: str = "Turkey",
                         target_date: Optional[date] = None) -> tuple[Optional[str], bool]:
    """Geriye dönük uyumluluk için: sadece öğle vaktini döndürür
    (eskiden Cuma namazı vakti için kullanılıyordu)."""
    timings, from_network = get_cached_or_fetch_day(city, country, target_date)
    return (timings.get("ogle") if timings else None), from_network


def compute_relative_time(hhmm: str, minutes: int, direction: str = "before") -> str:
    """Bir vakte göre 'önce' ya da 'sonra' bir saat hesaplar.
    Örnek: '13:12', 30, 'before' => '12:42'
           '13:12', 30, 'after'  => '13:42'"""
    base = datetime.strptime(hhmm, "%H:%M")
    delta = timedelta(minutes=minutes)
    result = base - delta if direction == "before" else base + delta
    return result.strftime("%H:%M")


def apply_offset_minutes(hhmm: str, minutes: int) -> str:
    """Bir vakte, işaretli (pozitif/negatif) dakika ekler - Temkin Süresi ve
    vakit/Sela'nın Dakika+Yön alanları için kullanılır (bkz. scheduler.py >
    _signed_offset). Pozitif değer sonraya, negatif değer öncesine kaydırır."""
    base = datetime.strptime(hhmm, "%H:%M")
    result = base + timedelta(minutes=minutes)
    return result.strftime("%H:%M")


# ---------- Kerahat vakitleri ----------
# Namaz kılmanın mekruh sayıldığı üç zaman dilimi: güneş doğarken (doğuştan
# itibaren ~45 dk), istiva vakti (güneşin tam tepede olduğu, öğleye çok kısa
# bir süre kala) ve güneş batarken (batıştan ~45 dk önce). Aladhan API bu
# aralıkları doğrudan vermediğinden, yaygın kabul gören sabit dakika
# yaklaşıklarıyla hesaplanır - hassas astronomik hesap değildir, "yaklaşık
# hatırlatma" amaçlıdır.
KERAHAT_GUNES_SONRASI_DK = 45
KERAHAT_ISTIVA_ONCESI_DK = 10
KERAHAT_AKSAM_ONCESI_DK = 45


def compute_kerahat_windows(timings: dict[str, str]) -> list[tuple[str, str, str]]:
    """[(etiket, başlangıç_HH:MM, bitiş_HH:MM), ...] döndürür."""
    windows = []
    if timings.get("gunes"):
        start = timings["gunes"]
        end = apply_offset_minutes(start, KERAHAT_GUNES_SONRASI_DK)
        windows.append(("Güneş Doğarken (Kerahat)", start, end))
    if timings.get("ogle"):
        end = timings["ogle"]
        start = apply_offset_minutes(end, -KERAHAT_ISTIVA_ONCESI_DK)
        windows.append(("İstiva Vakti (Kerahat)", start, end))
    if timings.get("aksam"):
        end = timings["aksam"]
        start = apply_offset_minutes(end, -KERAHAT_AKSAM_ONCESI_DK)
        windows.append(("Güneş Batarken (Kerahat)", start, end))
    return windows
