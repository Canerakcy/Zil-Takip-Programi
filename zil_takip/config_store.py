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


def default_daily_vakit() -> dict[str, Any]:
    """Günlük bir namaz vaktinin basit ayarı: açıksa, vakit girdiği ANDA
    (dakika/yön hesabı olmadan) seçilen ses çalınır."""
    return {"enabled": False, "sound": None}


def default_friday_offset(**overrides: Any) -> dict[str, Any]:
    """Cuma namazına özel, öğle/Cuma vaktine göre önce ya da sonra tetiklenen
    bağımsız bir zil kaydı - ör. namazdan 15 dk önce paydos zili, namazdan
    30 dk sonra mesaiye dönüş zili. İstediğiniz kadar kayıt eklenebilir."""
    offset = {
        "id": str(uuid.uuid4()),
        "minutes": 15,
        "direction": "before",  # "before" ya da "after"
        "label": "",  # boş bırakılırsa dakika/yöne göre otomatik üretilir
        "sound": None,
        "enabled": True,
    }
    offset.update(overrides)
    return offset


def default_friday_offsets() -> list[dict[str, Any]]:
    """Sıfırdan bir kurulumda gelen örnek kayıtlar - programın ilk sürümündeki
    Cuma namazı varsayılanlarıyla birebir aynı."""
    return [
        default_friday_offset(minutes=30, direction="before",
                               label="Cuma Namazı - 30 dk kala"),
        default_friday_offset(minutes=15, direction="before",
                               label="Cuma Namazı - 15 dk kala"),
        default_friday_offset(minutes=30, direction="after", enabled=False,
                               label="Cuma Namazı Sonrası - Mesaiye Dönüş (30 dk sonra)"),
    ]


def default_prayer_times() -> dict[str, Any]:
    return {
        "enabled": True,
        "city": "İstanbul",
        "country": "Turkey",
        # Günlük vakit sesi: her vakit kendi vaktinde, açıksa seçilen sesi çalar.
        "daily": {vakit: default_daily_vakit() for vakit in VAKIT_KEYS},
        # Cuma namazına özel, öğle/Cuma vaktine göre önce/sonra kayıtlar.
        "friday_offsets": default_friday_offsets(),
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
    # eski sürümlerdeki il/ilçe bilgisini koruyarak kendi kurar.
    defaults = default_config()
    for key, value in defaults.items():
        if key == "prayer_times":
            continue
        cfg.setdefault(key, value)

    old_friday = cfg.pop("friday_prayer", None)
    pt = cfg.setdefault("prayer_times", {})
    pt.setdefault("enabled", True)
    pt.setdefault("city", (old_friday or {}).get("city", "İstanbul"))
    pt.setdefault("country", (old_friday or {}).get("country", "Turkey"))
    pt.setdefault("en_ustte_goster", False)

    # "daily" (günlük vakit sesi) ve "friday_offsets" (Cuma namazına özel
    # önce/sonra kayıtları) - programın geçmişteki dört farklı sürümünden
    # göç edilebilir: (1) en eski "friday_prayer.offsets", (2) "alerts"
    # listesi (bir önceki sürüm), (3) "vakitler" + "sela" + "cuma_sela"
    # (ondan önceki sürüm), (4) hiçbiri yoksa sıfırdan kurulum. Idempotenttir.
    if "daily" not in pt or "friday_offsets" not in pt:
        daily = {vakit: default_daily_vakit() for vakit in VAKIT_KEYS}
        friday_offsets: list[dict[str, Any]] = []

        if old_friday and old_friday.get("offsets"):
            for off in old_friday["offsets"]:
                raw_sound = off.get("sound")
                friday_offsets.append(default_friday_offset(
                    minutes=off.get("minutes", 0),
                    direction=off.get("direction", "before"),
                    label=off.get("label", ""),
                    sound=None if raw_sound in (None, "default") else raw_sound,
                    enabled=off.get("enabled", True),
                ))
        elif "alerts" in pt:
            for alert in pt.get("alerts", []):
                if alert.get("friday_only"):
                    friday_offsets.append(default_friday_offset(
                        minutes=alert.get("minutes", 0),
                        direction=alert.get("direction", "before"),
                        label=alert.get("label", ""),
                        sound=alert.get("sound"),
                        enabled=alert.get("enabled", True),
                    ))
                else:
                    vakit = alert.get("vakit")
                    if vakit in daily and (alert.get("sesli") or alert.get("gorsel")):
                        daily[vakit] = {"enabled": alert.get("enabled", True),
                                         "sound": alert.get("sound")}
        elif "vakitler" in pt or "sela" in pt:
            for vakit, setting in pt.get("vakitler", {}).items():
                if vakit in daily and (setting.get("sesli") or setting.get("gorsel")):
                    daily[vakit] = {"enabled": True, "sound": setting.get("sound")}
            sela = pt.get("sela", {})
            if sela.get("sesli") or sela.get("gorsel"):
                friday_offsets.append(default_friday_offset(
                    minutes=sela.get("minutes_before", 0),
                    direction=sela.get("direction", "before"),
                    label="Sela",
                    sound=sela.get("sound"),
                    enabled=bool(pt.get("cuma_sela")),
                ))
        else:
            friday_offsets = default_friday_offsets()

        pt["daily"] = daily
        pt["friday_offsets"] = friday_offsets

    # Artık kullanılmayan eski alanlar temizlenir.
    for stale_key in ("vakitler", "sela", "cuma_sela", "alerts",
                       "gorsel_sonrasi_sesli", "kerahat_hatirlat", "temkin_suresi_dk"):
        pt.pop(stale_key, None)
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    path = get_config_path()
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    tmp_path.replace(path)
