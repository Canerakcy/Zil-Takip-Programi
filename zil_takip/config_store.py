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


def default_prayer_alert(vakit: str = "ogle", **overrides: Any) -> dict[str, Any]:
    """Bir namaz vaktine bağlı, bağımsız bir bildirim/zil kaydı. Her vakite
    istediğiniz kadar bağımsız kayıt eklenebilir (ör. Öğle için hem "30 dk
    önce uyarı" hem "tam vaktinde ezan" hem "Cuma günleri 30 dk sonra
    mesaiye dönüş" - üçü ayrı ayrı, aynı anda aktif olabilir)."""
    alert = {
        "id": str(uuid.uuid4()),
        "vakit": vakit,
        "label": "",  # boş bırakılırsa vakit adı + dakika/yöne göre otomatik üretilir
        "minutes": 0,
        # direction: "before" (vakitten X dk önce) ya da "after" (vakitten
        # X dk sonra, ör. mesaiye/derse dönüş zili).
        "direction": "before",
        "sesli": False,
        "gorsel": False,
        "sound": None,
        "enabled": True,
        # friday_only: sadece Cuma günleri çalışır - Cuma namazı/Sela gibi
        # sadece o güne özel kayıtlar için (öğle vaktinin kendisi normal
        # günlerde de vardır, bu kayıt sadece Cuma'ya özel davranış ekler).
        "friday_only": False,
    }
    alert.update(overrides)
    return alert


def default_prayer_alerts() -> list[dict[str, Any]]:
    """Sıfırdan bir kurulumda gelen örnek kayıtlar - eski 'Cuma Namazı'
    sekmesinin orijinal varsayılanlarıyla birebir aynı (30 dk ve 15 dk önce
    uyarı zili etkin, 30 dk sonra mesaiye dönüş zili örnek olarak eklenmiş
    ama kapalı)."""
    return [
        default_prayer_alert("ogle", minutes=30, direction="before", sesli=True,
                              friday_only=True, label="Cuma Namazı - 30 dk kala"),
        default_prayer_alert("ogle", minutes=15, direction="before", sesli=True,
                              friday_only=True, label="Cuma Namazı - 15 dk kala"),
        default_prayer_alert("ogle", minutes=30, direction="after", sesli=True,
                              friday_only=True, enabled=False,
                              label="Cuma Namazı Sonrası - Mesaiye Dönüş (30 dk sonra)"),
    ]


def default_prayer_times() -> dict[str, Any]:
    return {
        "enabled": True,
        "city": "İstanbul",
        "country": "Turkey",
        "alerts": default_prayer_alerts(),
        # "Görsel Uyarıdan Sonra Sese/Ezana Devam Et": açıksa önce görsel
        # uyarı gösterilir, kapatılınca ses çalınır (sıralı); kapalıysa
        # ikisi aynı anda başlar.
        "gorsel_sonrasi_sesli": False,
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
    pt.setdefault("gorsel_sonrasi_sesli", False)
    pt.setdefault("kerahat_hatirlat", False)
    pt.setdefault("temkin_suresi_dk", 0)
    pt.setdefault("en_ustte_goster", False)

    # "alerts" (her vakite birden fazla bağımsız kayıt eklenebilen esnek
    # liste) - üç farklı önceki sürümden göç edilebilir: (1) en eski
    # "friday_prayer.offsets", (2) bu oturumun bir önceki hali (tek satırlık
    # "vakitler" sözlüğü + ayrı "sela" + "cuma_sela"), (3) hiçbiri yoksa
    # sıfırdan kurulum. Idempotenttir - "alerts" zaten varsa dokunulmaz.
    if "alerts" not in pt:
        alerts: list[dict[str, Any]] = []
        if old_friday and old_friday.get("offsets"):
            for off in old_friday["offsets"]:
                raw_sound = off.get("sound")
                alerts.append(default_prayer_alert(
                    "ogle",
                    label=off.get("label", ""),
                    minutes=off.get("minutes", 0),
                    direction=off.get("direction", "before"),
                    sesli=True, gorsel=False,
                    sound=None if raw_sound in (None, "default") else raw_sound,
                    enabled=off.get("enabled", True),
                    friday_only=True,
                ))
        elif "vakitler" in pt or "sela" in pt:
            for vakit, setting in pt.get("vakitler", {}).items():
                if setting.get("sesli") or setting.get("gorsel"):
                    alerts.append(default_prayer_alert(
                        vakit,
                        minutes=setting.get("minutes_before", 0),
                        direction=setting.get("direction", "before"),
                        sesli=setting.get("sesli", False),
                        gorsel=setting.get("gorsel", False),
                        sound=setting.get("sound"),
                    ))
            sela = pt.get("sela", {})
            if sela.get("sesli") or sela.get("gorsel"):
                alerts.append(default_prayer_alert(
                    "ogle", label="Sela",
                    minutes=sela.get("minutes_before", 0),
                    direction=sela.get("direction", "before"),
                    sesli=sela.get("sesli", False),
                    gorsel=sela.get("gorsel", False),
                    sound=sela.get("sound"),
                    enabled=bool(pt.get("cuma_sela")),
                    friday_only=True,
                ))
        else:
            alerts = default_prayer_alerts()
        pt["alerts"] = alerts

    # Artık kullanılmayan eski alanlar temizlenir.
    pt.pop("vakitler", None)
    pt.pop("sela", None)
    pt.pop("cuma_sela", None)
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    path = get_config_path()
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    tmp_path.replace(path)
