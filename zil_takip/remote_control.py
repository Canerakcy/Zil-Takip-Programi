"""Cihaz eşleştirme ve uzaktan müdahale - internet/sunucu gerektirmeden,
yalnızca yerel ağ (aynı WiFi/LAN) üzerinden çalışır.

Protokol özeti:
- Eşleştirme keşfi UDP yayını (broadcast) ile yapılır (PAIRING_UDP_PORT).
  Bağlanmak isteyen cihaz, girilen kodu içeren bir "pair_request" paketini
  yerel ağa yayınlar. Kodu üreten (host) cihaz kodu tanırsa hemen bir
  "pair_ack" gönderir (karşı tarafta "onay bekleniyor" gösterilsin diye),
  sonra kullanıcıya onay diyaloğu gösterir; kullanıcı Evet/Hayır dedikten
  sonra "pair_response" (approved: true/false, approved ise bir token) UDP
  ile isteği yapan cihaza geri gönderilir.
- Eşleştirmeden sonraki tüm komutlar (zil çal/durdur, ayar oku/yaz) TCP
  üzerinden, satır satır JSON mesajlarla yürütülür (CONTROL_TCP_PORT).
  Her bağlantı önce paylaşılan token ile kimlik doğrular.
- Cihazların IP'si zamanla değişebileceğinden (DHCP), bağlanılamazsa aynı
  UDP portu üzerinden "locate_request" ile eşleşmiş cihaz güncel IP'sini
  yeniden bulur (token'a göre eşleştirilir).
"""
from __future__ import annotations

import json
import random
import socket
import string
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

PAIRING_UDP_PORT = 47601
CONTROL_TCP_PORT = 47602
PROTOCOL_VERSION = 1
PAIRING_CODE_TTL_SECONDS = 300  # üretilen kod 5 dakika sonra geçersiz olur
DISCOVERY_TIMEOUT_SECONDS = 20  # kod ile bağlanmaya çalışırken beklenecek azami süre
LOCATE_TIMEOUT_SECONDS = 5


def generate_pairing_code() -> str:
    """5-20 hane arası rastgele bir sayısal eşleştirme kodu üretir."""
    length = random.randint(5, 20)
    digits = [random.choice(string.digits) for _ in range(length)]
    # Baştaki sıfırları göstermek/karışıklığı önlemek için ilk hane 1-9 olsun.
    digits[0] = random.choice(string.digits[1:])
    return "".join(digits)


def generate_token() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex  # 64 hex karakter


def _get_local_hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "Bilinmeyen Cihaz"


@dataclass
class PairedDevice:
    """Bu cihazın eşleştiği (bağlanabildiği) bir uzak cihaz kaydı."""
    peer_id: str
    name: str
    token: str
    last_known_ip: Optional[str] = None
    control_port: int = CONTROL_TCP_PORT

    def to_json(self) -> dict[str, Any]:
        return {
            "peer_id": self.peer_id,
            "name": self.name,
            "token": self.token,
            "last_known_ip": self.last_known_ip,
            "control_port": self.control_port,
        }

    @staticmethod
    def from_json(data: dict[str, Any]) -> "PairedDevice":
        return PairedDevice(
            peer_id=data["peer_id"],
            name=data.get("name", "Bilinmeyen Cihaz"),
            token=data["token"],
            last_known_ip=data.get("last_known_ip"),
            control_port=data.get("control_port", CONTROL_TCP_PORT),
        )


def _send_udp_broadcast(sock: socket.socket, payload: dict[str, Any]) -> None:
    data = (json.dumps(payload) + "\n").encode("utf-8")
    sock.sendto(data, ("<broadcast>", PAIRING_UDP_PORT))


def _send_udp_to(sock: socket.socket, payload: dict[str, Any], addr: tuple[str, int]) -> None:
    data = (json.dumps(payload) + "\n").encode("utf-8")
    sock.sendto(data, addr)


class RemoteControlManager:
    """Hem "başka bir cihaz beni eşleştirsin/kontrol etsin" (host) hem de
    "ben başka bir cihaza bağlanayım" (client) taraflarını yönetir.

    Kullanım (uygulama tarafında):
        rc = RemoteControlManager(
            get_config=lambda: app.cfg,
            apply_remote_config=lambda cfg: app.apply_remote_config(cfg),
            ring_now=lambda sound: audio_player.play_file(...),
            stop_ringing=lambda: audio_player.stop(),
            on_pairing_request=lambda name, code, decide: ...,  # onay diyaloğu göster
            on_log=lambda msg: ...,
        )
        rc.start()
    """

    def __init__(
        self,
        get_config: Callable[[], dict[str, Any]],
        apply_remote_config: Callable[[dict[str, Any]], None],
        ring_now: Callable[[Optional[str]], None],
        stop_ringing: Callable[[], None],
        on_pairing_request: Callable[[str, Callable[[bool], None]], None],
        on_log: Callable[[str], None],
        device_name: Optional[str] = None,
        on_devices_changed: Optional[Callable[[], None]] = None,
        initial_paired_devices: Optional[list["PairedDevice"]] = None,
    ) -> None:
        self._get_config = get_config
        self._apply_remote_config = apply_remote_config
        self._ring_now = ring_now
        self._stop_ringing = stop_ringing
        self._on_pairing_request = on_pairing_request
        self._on_log = on_log
        self._on_devices_changed_cb = on_devices_changed
        self.device_name = device_name or _get_local_hostname()
        self.paired_devices: list[PairedDevice] = list(initial_paired_devices or [])

        self._udp_sock: Optional[socket.socket] = None
        self._tcp_server: Optional[socket.socket] = None
        self._stop_event = threading.Event()

        self._active_code: Optional[str] = None
        self._active_code_expires_at: float = 0.0
        self._lock = threading.Lock()

    # ---------- Yaşam döngüsü ----------
    def start(self) -> None:
        self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._udp_sock.bind(("", PAIRING_UDP_PORT))

        self._tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._tcp_server.bind(("", CONTROL_TCP_PORT))
        self._tcp_server.listen(5)

        threading.Thread(target=self._udp_listen_loop, daemon=True).start()
        threading.Thread(target=self._tcp_listen_loop, daemon=True).start()

    def stop(self) -> None:
        self._stop_event.set()
        for sock in (self._udp_sock, self._tcp_server):
            try:
                if sock is not None:
                    sock.close()
            except Exception:
                pass

    # ---------- Host tarafı: eşleştirme kodu üretme ----------
    def generate_code(self) -> str:
        with self._lock:
            self._active_code = generate_pairing_code()
            self._active_code_expires_at = time.time() + PAIRING_CODE_TTL_SECONDS
            return self._active_code

    def cancel_code(self) -> None:
        with self._lock:
            self._active_code = None

    def _current_code(self) -> Optional[str]:
        with self._lock:
            if self._active_code and time.time() < self._active_code_expires_at:
                return self._active_code
            self._active_code = None
            return None

    # ---------- UDP dinleme (keşif + eşleştirme) ----------
    def _udp_listen_loop(self) -> None:
        sock = self._udp_sock
        assert sock is not None
        while not self._stop_event.is_set():
            try:
                data, addr = sock.recvfrom(4096)
            except OSError:
                return
            try:
                msg = json.loads(data.decode("utf-8").strip())
            except (ValueError, UnicodeDecodeError):
                continue
            try:
                self._handle_udp_message(msg, addr)
            except Exception as exc:
                self._on_log(f"Eşleştirme mesajı işlenemedi: {exc}")

    def _handle_udp_message(self, msg: dict[str, Any], addr: tuple[str, int]) -> None:
        msg_type = msg.get("type")

        if msg_type == "pair_request":
            code = self._current_code()
            if not code or msg.get("code") != code:
                return  # bu bizim kodumuz değil - sessizce yok say
            requester_name = str(msg.get("name") or "Bilinmeyen Cihaz")
            _send_udp_to(self._udp_sock, {"v": PROTOCOL_VERSION, "type": "pair_ack"}, addr)

            def decide(approved: bool) -> None:
                if approved:
                    token = generate_token()
                    peer = PairedDevice(peer_id=uuid.uuid4().hex, name=requester_name,
                                         token=token, last_known_ip=addr[0])
                    self.paired_devices.append(peer)
                    self._on_devices_changed()
                    _send_udp_to(self._udp_sock, {
                        "v": PROTOCOL_VERSION, "type": "pair_response", "approved": True,
                        "host_name": self.device_name, "token": token,
                        "control_port": CONTROL_TCP_PORT,
                    }, addr)
                    self._on_log(f"'{requester_name}' bu cihazla eşleşti (uzaktan müdahale açık).")
                else:
                    _send_udp_to(self._udp_sock, {
                        "v": PROTOCOL_VERSION, "type": "pair_response", "approved": False,
                    }, addr)
                with self._lock:
                    self._active_code = None

            self._on_pairing_request(requester_name, decide)

        elif msg_type == "locate_request":
            token = msg.get("token")
            match = next((p for p in self.paired_devices if p.token == token), None)
            if match is not None:
                _send_udp_to(self._udp_sock, {
                    "v": PROTOCOL_VERSION, "type": "locate_response",
                    "control_port": CONTROL_TCP_PORT, "host_name": self.device_name,
                }, addr)

    # ---------- Client tarafı: koda göre eşleştirme isteği gönder ----------
    def pair_with_code(self, code: str, on_status: Callable[[str], None]) -> Optional[PairedDevice]:
        """Girilen kodu yerel ağa yayınlar, karşı taraf onaylarsa eşleşmiş
        cihaz kaydını döndürür (senkron/bloklayan bir çağrıdır - ayrı bir
        thread'den çağırın). on_status ile ara durumlar bildirilir."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", 0))
        sock.settimeout(1.0)
        try:
            request = {"v": PROTOCOL_VERSION, "type": "pair_request", "code": code,
                       "name": self.device_name}
            deadline = time.time() + DISCOVERY_TIMEOUT_SECONDS
            got_ack = False
            _send_udp_broadcast(sock, request)
            last_broadcast = time.time()
            on_status("Aranıyor...")
            while time.time() < deadline:
                if not got_ack and time.time() - last_broadcast > 2.0:
                    _send_udp_broadcast(sock, request)
                    last_broadcast = time.time()
                try:
                    data, addr = sock.recvfrom(4096)
                except socket.timeout:
                    continue
                try:
                    msg = json.loads(data.decode("utf-8").strip())
                except (ValueError, UnicodeDecodeError):
                    continue
                if msg.get("type") == "pair_ack" and not got_ack:
                    got_ack = True
                    on_status("İstek gönderildi, karşı cihazda onay bekleniyor...")
                    deadline = time.time() + 90  # insan onayı için daha uzun süre tanı
                elif msg.get("type") == "pair_response":
                    if not msg.get("approved"):
                        on_status("Karşı cihaz isteği reddetti.")
                        return None
                    peer = PairedDevice(
                        peer_id=uuid.uuid4().hex,
                        name=str(msg.get("host_name") or "Bilinmeyen Cihaz"),
                        token=str(msg["token"]),
                        last_known_ip=addr[0],
                        control_port=int(msg.get("control_port", CONTROL_TCP_PORT)),
                    )
                    self.paired_devices.append(peer)
                    self._on_devices_changed()
                    on_status(f"'{peer.name}' ile eşleşti.")
                    return peer
            on_status("Zaman aşımı - kod bulunamadı ya da onaylanmadı.")
            return None
        finally:
            sock.close()

    def _locate(self, peer: PairedDevice) -> Optional[str]:
        """Eşleşmiş bir cihazın güncel IP'sini yeniden bulur (IP değişmiş
        olabilir - ör. DHCP kira yenilemesi)."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", 0))
        sock.settimeout(0.5)
        try:
            request = {"v": PROTOCOL_VERSION, "type": "locate_request", "token": peer.token}
            deadline = time.time() + LOCATE_TIMEOUT_SECONDS
            _send_udp_broadcast(sock, request)
            while time.time() < deadline:
                try:
                    data, addr = sock.recvfrom(4096)
                except socket.timeout:
                    continue
                try:
                    msg = json.loads(data.decode("utf-8").strip())
                except (ValueError, UnicodeDecodeError):
                    continue
                if msg.get("type") == "locate_response":
                    peer.last_known_ip = addr[0]
                    peer.control_port = int(msg.get("control_port", CONTROL_TCP_PORT))
                    return addr[0]
            return None
        finally:
            sock.close()

    # ---------- Client tarafı: uzak cihaza komut gönderme ----------
    def send_command(self, peer: PairedDevice, cmd: dict[str, Any],
                      timeout: float = 8.0) -> dict[str, Any]:
        """Eşleşmiş bir cihaza tek bir komut gönderip yanıtını döndürür.
        Bağlanılamazsa cihazı yeniden bulmayı (locate) bir kez dener."""
        last_error: Optional[Exception] = None
        for attempt in range(2):
            ip = peer.last_known_ip
            if ip is None or attempt == 1:
                ip = self._locate(peer)
                if ip is None:
                    last_error = ConnectionError("Cihaz ağda bulunamadı.")
                    continue
            try:
                return self._send_command_to(ip, peer.control_port, peer.token, cmd, timeout)
            except OSError as exc:
                last_error = exc
                peer.last_known_ip = None  # bir dahaki denemede yeniden bulmayı zorla
        raise ConnectionError(str(last_error) if last_error else "Bağlanılamadı.")

    def _send_command_to(self, ip: str, port: int, token: str, cmd: dict[str, Any],
                          timeout: float) -> dict[str, Any]:
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            sock_file = sock.makefile("rwb")
            self._write_json(sock_file, {"type": "auth", "token": token})
            auth_result = self._read_json(sock_file, timeout)
            if not auth_result.get("ok"):
                raise PermissionError("Kimlik doğrulama reddedildi (eşleştirme kaldırılmış olabilir).")
            self._write_json(sock_file, {"type": "cmd", **cmd})
            return self._read_json(sock_file, timeout)

    @staticmethod
    def _write_json(sock_file, payload: dict[str, Any]) -> None:
        sock_file.write((json.dumps(payload) + "\n").encode("utf-8"))
        sock_file.flush()

    @staticmethod
    def _read_json(sock_file, timeout: float) -> dict[str, Any]:
        line = sock_file.readline()
        if not line:
            raise ConnectionError("Bağlantı karşı taraftan kapatıldı.")
        return json.loads(line.decode("utf-8").strip())

    # ---------- Host tarafı: TCP komut sunucusu ----------
    def _tcp_listen_loop(self) -> None:
        server = self._tcp_server
        assert server is not None
        while not self._stop_event.is_set():
            try:
                conn, addr = server.accept()
            except OSError:
                return
            threading.Thread(target=self._handle_tcp_connection, args=(conn, addr),
                              daemon=True).start()

    def _handle_tcp_connection(self, conn: socket.socket, addr: tuple[str, int]) -> None:
        try:
            conn.settimeout(30)
            sock_file = conn.makefile("rwb")
            auth_msg = self._read_json(sock_file, 30)
            if auth_msg.get("type") != "auth":
                return
            token = auth_msg.get("token")
            peer = next((p for p in self.paired_devices if p.token == token), None)
            if peer is None:
                self._write_json(sock_file, {"ok": False})
                return
            peer.last_known_ip = addr[0]
            self._write_json(sock_file, {"ok": True})

            cmd_msg = self._read_json(sock_file, 30)
            result = self._execute_command(cmd_msg, peer)
            self._write_json(sock_file, result)
        except Exception as exc:
            self._on_log(f"Uzaktan müdahale bağlantı hatası: {exc}")
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _execute_command(self, msg: dict[str, Any], peer: PairedDevice) -> dict[str, Any]:
        cmd = msg.get("cmd")
        try:
            if cmd == "ring_now":
                self._ring_now(msg.get("sound"))
                self._on_log(f"'{peer.name}' zili şimdi çaldırdı (uzaktan müdahale).")
                return {"ok": True}
            if cmd == "stop":
                self._stop_ringing()
                return {"ok": True}
            if cmd == "get_config":
                return {"ok": True, "data": self._get_config()}
            if cmd == "set_config":
                new_cfg = msg.get("config")
                if not isinstance(new_cfg, dict):
                    return {"ok": False, "error": "Geçersiz ayar verisi."}
                self._apply_remote_config(new_cfg)
                self._on_log(f"'{peer.name}' ayarları uzaktan değiştirdi.")
                return {"ok": True}
            return {"ok": False, "error": f"Bilinmeyen komut: {cmd}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ---------- Eşleşmiş cihaz listesi değişiklik bildirimi ----------
    def _on_devices_changed(self) -> None:
        if self._on_devices_changed_cb is not None:
            self._on_devices_changed_cb()

    def remove_paired_device(self, peer_id: str) -> None:
        self.paired_devices = [p for p in self.paired_devices if p.peer_id != peer_id]
        self._on_devices_changed()
