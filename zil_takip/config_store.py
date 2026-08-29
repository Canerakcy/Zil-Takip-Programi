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
        "friday_prayer": {
            "enabled": True,
            "city": "İstanbul",
            "country": "Turkey",
            "offsets": [
                {"minutes": 30, "direction": "before", "enabled": True, "sound": "default",
                 "label": "Cuma Namazı - 30 dk kala"},
                {"minutes": 15, "direction": "before", "enabled": True, "sound": "default",
                 "label": "Cuma Namazı - 15 dk kala"},
                {"minutes": 30, "direction": "after", "enabled": False, "sound": "default",
                 "label": "Cuma Namazı Sonrası - Mesaiye Dönüş (30 dk sonra)"},
            ],
        },
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

    # Eksik alanları varsayılanlarla tamamla (ileriye dönük uyumluluk için)
    defaults = default_config()
    for key, value in defaults.items():
        cfg.setdefault(key, value)
    cfg["friday_prayer"].setdefault("enabled", True)
    cfg["friday_prayer"].setdefault("city", "İstanbul")
    cfg["friday_prayer"].setdefault("country", "Turkey")
    cfg["friday_prayer"].setdefault("offsets", defaults["friday_prayer"]["offsets"])
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    path = get_config_path()
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    tmp_path.replace(path)
