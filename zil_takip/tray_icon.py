"""Sistem tepsisi (system tray) simgesi ve menüsü.

pystray'in menü tıklamaları kendi thread'inde çalıştığı için Tkinter
nesnelerine doğrudan dokunmuyoruz; bunun yerine bir kuyruğa komut
bırakıyoruz, Tkinter tarafı bu kuyruğu periyodik olarak okuyor."""
from __future__ import annotations

import queue
import threading
from typing import Optional

from PIL import Image, ImageDraw
import pystray

SHOW = "show"
QUIT = "quit"


def _create_icon_image() -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((3, 3, size - 3, size - 3), fill=(31, 74, 52, 255))
    draw.ellipse((16, 14, size - 16, size - 28), fill=(255, 255, 255, 255))
    draw.polygon(
        [(size / 2 - 7, size - 26), (size / 2 + 7, size - 26), (size / 2, size - 12)],
        fill=(255, 255, 255, 255))
    return img


class TrayIcon:
    """Kapatılınca yok olmayan, arka planda çalışan sistem tepsisi simgesi."""

    def __init__(self):
        self.commands: "queue.Queue[str]" = queue.Queue()
        self._icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._icon = pystray.Icon(
            "ceselsan_zil_takip",
            _create_icon_image(),
            "Ceselsan Zil Takip Programı",
            menu=pystray.Menu(
                pystray.MenuItem("Göster", lambda: self.commands.put(SHOW), default=True),
                pystray.MenuItem("Çıkış", lambda: self.commands.put(QUIT)),
            ),
        )
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._icon is not None:
            self._icon.stop()
