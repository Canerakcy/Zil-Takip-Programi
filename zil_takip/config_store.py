"""Ayarların diske kaydedilip okunmasından sorumlu modül."""
from __future__ import annotations

import json
import os
import platform
import uuid
from pathlib import Path
from typing import Any


APP_DIR_NAME = "ZilTakipProgrami"
CONFIG_FILE_NAME = "config.json"


def get_app_data_dir() -> Path:
    """Windows'ta %APPDATA%, diğer sistemlerde kullanıcı home dizini altında
    ayar klasörünü döndürür ve gerekirse oluşturur."""
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA") or str(Path.home())
    else:
        base = str(Path.home() / ".config")
    path = Path(base) / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_config_path() -> Path:
    return get_app_data_dir() / CONFIG_FILE_NAME


VAKIT_KEYS = ["imsak", "gunes", "ogle", "ikindi", "aksam", "yatsi"]


def default_vakit_setting() -> dict[str, Any]:
    # direction: "before" (vakitten X dk önce) ya da "after" (vakitten X dk
    # sonra, ör. mesaiye/derse dönüş zili) - kurumların mola süresi farklı
    # olduğundan her iki yön de desteklenir.
    return {"sesli": False, "gorsel": False, "sound": None,
            "minutes_before": 0, "direction": "before"}


def default_prayer_times() -> dict[str, Any]:
    return {
        "enabled": True,
        "city": "İstanbul",
        "country": "Turkey",
        "vakitler": {vakit: default_vakit_setting() for vakit in VAKIT_KEYS},
        # Sela, öğle vaktine göre (genelde Cuma günü) ayrı bir kayıt olarak okunur.
        "sela": {"sesli": False, "gorsel": False, "sound": None,
                 "minutes_before": 60, "direction": "before"},
        # "Görsel Uyandan sonra Ezana Devam Et": açıksa önce görsel uyarı
        # gösterilir, kapatılınca sesli ezan/zil çalınır (sıralı); kapalıysa
        # ikisi aynı anda başlar.
        "gorsel_sonrasi_sesli": False,
        # "Cuma Günleri Sela Oku": sadece sela kaydını Cuma günleri tetikler.
        "cuma_sela": False,
        "kerahat_hatirlat": False,
        # Temkin Süresi (dk): hesaplanan tüm vakitlere eklenen güvenlik payı,
        # negatif de olabilir (örn. -5 => 5 dk erken).
        "temkin_suresi_dk": 0,
        "en_ustte_goster": False,
    }


def default_config() -> dict[str, Any]:
    return {
        "output_device": None,  # sounddevice cihaz adı (string) ya da None -> sistem varsayılanı
        "default_sound": None,  # kullanıcının Ses Ayarları'ndan seçtiği ses dosyasının yolu
        "volume": 1.0,
        "entries": [
            {
                "id": str(uuid.uuid4()),
                "label": "1. Ders Başlangıcı",
                "time": "08:30",
                "days": [0, 1, 2, 3, 4],  # Pazartesi=0 ... Cuma=4
                "sound": "default",
                "enabled": True,
            },
        ],
        "prayer_times": default_prayer_times(),
        "minimize_to_tray": True,
        "start_with_windows": False,
        # {"date": "YYYY-AA-GG", "label": "..."} formatında; bu tarihlerde hiç zil çalmaz
        "holidays": [],
    }


def load_config() -> dict[str, Any]:
    path = get_config_path()
    if not path.exists():
        cfg = default_config()
        save_config(cfg)
        return cfg
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (json.JSONDecodeError, OSError):
        cfg = default_config()
        save_config(cfg)
        return cfg

    # Eksik alanları varsayılanlarla tamamla (ileriye dönük uyumluluk için).
    # "prayer_times" burada KASITLI olarak atlanır - aşağıdaki göç bloğu onu
    # eski "friday_prayer" içindeki il/ilçe bilgisini koruyarak kendi kurar;
    # burada genel setdefault ile doldurulursa (city="İstanbul" dahil) göç
    # bloğundaki pt.setdefault("city", ...) hiçbir zaman devreye giremez.
    defaults = default_config()
    for key, value in defaults.items():
        if key == "prayer_times":
            continue
        cfg.setdefault(key, value)

    # Eski "friday_prayer" (sadece Cuma/öğle önce-sonra zili) yapısından,
    # tüm günlük vakitleri kapsayan "prayer_times" yapısına geçiş: eski il/
    # ilçe bilgisi korunur, geri kalanı yeni varsayılanlarla başlar - eski
    # alan artık kullanılmadığından siline
    old_friday = cfg.pop("friday_prayer", None)
    # DİKKAT: setdefault'a default_prayer_times() (zaten city="İstanbul" dolu
    # gelen) verilirse, aşağıdaki pt.setdefault("city", ...) hiçbir zaman
    # devreye giremez - o yüzden burada bilerek BOŞ bir sözlükle başlanır,
    # her alan kendi (eski veriyi koruyan) varsayılanıyla tek tek doldurulur.
    pt = cfg.setdefault("prayer_times", {})
    pt.setdefault("enabled", True)
    pt.setdefault("city", (old_friday or {}).get("city", "İstanbul"))
    pt.setdefault("country", (old_friday or {}).get("country", "Turkey"))
    vakitler = pt.setdefault("vakitler", {})
    for vakit in VAKIT_KEYS:
        setting = vakitler.setdefault(vakit, default_vakit_setting())
        # "direction" alanı sonradan eklendi - önceki bir sürümle kaydedilmiş
        # bir vakit ayarında eksik olabilir, tek tek tamamlanır.
        setting.setdefault("direction", "before")
    sela = pt.setdefault("sela", default_prayer_times()["sela"])
    sela.setdefault("direction", "before")
    pt.setdefault("gorsel_sonrasi_sesli", False)
    pt.setdefault("cuma_sela", False)
    pt.setdefault("kerahat_hatirlat", False)
    pt.setdefault("temkin_suresi_dk", 0)
    pt.setdefault("en_ustte_goster", False)
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    path = get_config_path()
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    tmp_path.replace(path)
