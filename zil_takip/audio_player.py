"""Ses cihazı listeleme ve seçilen hoparlörden ses çalma işlemleri."""
from __future__ import annotations

import threading
from dataclasses import dataclass

import numpy as np
import sounddevice as sd
import soundfile as sf


@dataclass
class OutputDevice:
    index: int
    name: str
    host_api: str

    def display_name(self) -> str:
        return f"{self.name} ({self.host_api})"


def list_output_devices() -> list[OutputDevice]:
    """Sistemdeki tüm çıkış (hoparlör/kulaklık) cihazlarını döndürür."""
    devices = []
    try:
        host_apis = sd.query_hostapis()
        for idx, dev in enumerate(sd.query_devices()):
            if dev.get("max_output_channels", 0) > 0:
                host_api_name = host_apis[dev["hostapi"]]["name"]
                devices.append(OutputDevice(index=idx, name=dev["name"], host_api=host_api_name))
    except Exception:
        pass
    return devices


def find_device_index_by_name(name: str | None) -> int | None:
    """Kaydedilmiş cihaz adına göre güncel cihaz listesindeki index'i bulur.
    Sistem her açılışta cihazları farklı sırada döndürebileceği için
    index yerine isim saklanır ve burada eşleştirilir."""
    if not name:
        return None
    for dev in list_output_devices():
        if dev.name == name:
            return dev.index
    return None


def resolve_sound_path(sound_value: str | None, default_sound: str | None) -> str:
    """Bir zil kaydının hangi ses dosyasını kullanacağını belirler.
    'default' ya da boş bırakılmışsa, Ses Ayarları'nda kullanıcının
    seçtiği genel varsayılan ses dosyası kullanılır. Ses üretilmez;
    kullanıcı mutlaka kendi ses dosyasını seçmelidir."""
    path = sound_value if sound_value and sound_value != "default" else default_sound
    if not path:
        raise ValueError(
            "Çalınacak ses dosyası seçilmemiş. Lütfen 'Ses Ayarları' sekmesinden "
            "veya bu kayıt için bir ses dosyası seçin.")
    return path


def play_file(sound_value: str | None, device_name: str | None,
              default_sound: str | None = None, volume: float = 1.0,
              blocking: bool = False) -> None:
    """Belirtilen ses dosyasını seçilen çıkış cihazından çalar.
    Cihaz bulunamazsa sistem varsayılan hoparlörü kullanılır."""
    path = resolve_sound_path(sound_value, default_sound)
    data, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    data = np.clip(data * volume, -1.0, 1.0)
    device_index = find_device_index_by_name(device_name)

    def _play():
        sd.play(data, sample_rate, device=device_index)
        if blocking:
            sd.wait()

    if blocking:
        _play()
    else:
        threading.Thread(target=_play, daemon=True).start()


def stop() -> None:
    sd.stop()
