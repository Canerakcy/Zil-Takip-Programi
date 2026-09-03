"""Uygulamanın aynı anda birden fazla kopyasının çalışmasını engeller.

Program zaten arka planda (sistem tepsisinde ya da normal pencerede)
çalışırken exe'ye tekrar tıklanırsa: ikinci süreç bunu fark eder, çalışan
sürece "pencereyi öne getir" sinyalini gönderir ve hemen kapanır - yeni bir
pencere açılmaz, aynı ayar dosyasına iki süreçten aynı anda yazılmaz.

Kilit, 127.0.0.1 üzerinde sabit bir porta bağlanmaya çalışarak tutulur:
bağlanabilen ilk süreç birincil örnektir, bağlanamayan her sonraki süreç
zaten bir örneğin çalıştığını anlar.
"""
from __future__ import annotations

import queue
import socket
import threading
from typing import Optional

_HOST = "127.0.0.1"
_PORT = 51823
_SHOW = b"SHOW"


class SingleInstance:
    def __init__(self) -> None:
        self._server: Optional[socket.socket] = None
        self.show_requests: "queue.Queue[bool]" = queue.Queue()

    def acquire(self) -> bool:
        """Bu süreç birincil örnekse dinlemeye başlar ve True döner."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind((_HOST, _PORT))
        except OSError:
            server.close()
            return False
        server.listen(5)
        self._server = server
        threading.Thread(target=self._listen, daemon=True).start()
        return True

    def _listen(self) -> None:
        server = self._server
        if server is None:
            return
        while True:
            try:
                conn, _addr = server.accept()
            except OSError:
                return
            with conn:
                try:
                    if conn.recv(16) == _SHOW:
                        self.show_requests.put(True)
                except OSError:
                    pass

    def close(self) -> None:
        if self._server is not None:
            try:
                self._server.close()
            finally:
                self._server = None


def notify_running_instance() -> bool:
    """Zaten çalışan örneğe pencereyi öne getirmesini söyler.

    Çalışan bir örnek bulunup bilgilendirildiyse True döner.
    """
    try:
        with socket.create_connection((_HOST, _PORT), timeout=2) as sock:
            sock.sendall(_SHOW)
        return True
    except OSError:
        return False
