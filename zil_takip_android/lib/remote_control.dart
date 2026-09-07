// Cihaz eşleştirme ve uzaktan müdahale - internet/sunucu gerektirmeden,
// yalnızca yerel ağ (aynı WiFi/LAN) üzerinden çalışır. Windows sürümündeki
// remote_control.py ile TAMAMEN AYNI kablo protokolünü konuşur (aynı port
// numaraları, aynı JSON mesaj tipleri/alan adları) - böylece bir Android
// telefonu bir Windows bilgisayarla (ya da tam tersi) eşleşip birbirini
// uzaktan yönetebilir.
//
// Protokol özeti:
// - Eşleştirme keşfi UDP yayını (broadcast) ile yapılır (pairingUdpPort).
//   Bağlanmak isteyen cihaz, girilen kodu içeren bir "pair_request" paketini
//   yerel ağa yayınlar. Kodu üreten (host) cihaz kodu tanırsa hemen bir
//   "pair_ack" gönderir, sonra kullanıcıya onay isteği gösterir; kullanıcı
//   evet/hayır dedikten sonra "pair_response" (approved + token) UDP ile
//   isteği yapan cihaza geri gönderilir.
// - Eşleştirmeden sonraki tüm komutlar (zil çal/durdur, ayar oku/yaz) TCP
//   üzerinden, satır satır JSON mesajlarla yürütülür (controlTcpPort). Her
//   bağlantı önce paylaşılan token ile kimlik doğrular.
// - IP'ler zamanla değişebileceğinden (DHCP), bağlanılamazsa aynı UDP portu
//   üzerinden "locate_request" ile eşleşmiş cihazın güncel IP'si bulunur.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'ring_history.dart';

const int pairingUdpPort = 47601;
const int controlTcpPort = 47602;
const int protocolVersion = 1;
const int pairingCodeTtlSeconds = 300; // üretilen kod, kimse girmeden 5 dakika sonra geçersiz olur
const int discoveryTimeoutSeconds = 20; // kod ile bağlanmaya çalışırken (karşı taraf bulunana kadar) beklenecek azami süre
const int approvalTimeoutSeconds = 30; // karşı cihazda onay diyaloğu bu süre içinde yanıtlanmazsa otomatik reddedilir
const int locateTimeoutSeconds = 5;
const int configExportCodeTtlSeconds = 300; // ayar aktarım kodu, kimse girmeden 5 dakika sonra geçersiz olur
const int configExportGrantTtlSeconds = 30; // UDP eşleşmesinden sonra TCP ile bağlanmak için azami süre
const int configExportDiscoveryTimeoutSeconds = 20; // kod ile ayar isterken azami bekleme süresi

final Random _random = Random.secure();

/// 5-20 hane arası rastgele bir sayısal eşleştirme kodu üretir.
String generatePairingCode() {
  final length = 5 + _random.nextInt(16);
  final buffer = StringBuffer()..write((1 + _random.nextInt(9)).toString());
  for (var i = 1; i < length; i++) {
    buffer.write(_random.nextInt(10).toString());
  }
  return buffer.toString();
}

String generateToken() {
  const chars = '0123456789abcdef';
  return List.generate(64, (_) => chars[_random.nextInt(16)]).join();
}

String _generatePeerId() {
  const chars = '0123456789abcdef';
  return List.generate(32, (_) => chars[_random.nextInt(16)]).join();
}

class PairedDevice {
  String peerId;
  String name;
  String token;
  String? lastKnownIp;
  int controlPort;

  PairedDevice({
    required this.peerId,
    required this.name,
    required this.token,
    this.lastKnownIp,
    this.controlPort = controlTcpPort,
  });

  Map<String, dynamic> toJson() => {
        'peer_id': peerId,
        'name': name,
        'token': token,
        'last_known_ip': lastKnownIp,
        'control_port': controlPort,
      };

  factory PairedDevice.fromJson(Map<String, dynamic> json) => PairedDevice(
        peerId: json['peer_id'] as String,
        name: json['name'] as String? ?? 'Bilinmeyen Cihaz',
        token: json['token'] as String,
        lastKnownIp: json['last_known_ip'] as String?,
        controlPort: (json['control_port'] as num?)?.toInt() ?? controlTcpPort,
      );
}

/// Bir soketten satır satır (newline-delimited) JSON mesajı okumak için -
/// dart:io Socket'i tek-abonelikli (single-subscription) bir Stream olduğu
/// için art arda birden fazla mesaj okumak üzere elle tamponlanır.
class _LineReader {
  final StreamSubscription<List<int>> _sub;
  final List<int> _buffer = [];
  final List<Completer<String>> _pending = [];
  Object? _error;

  _LineReader(Stream<List<int>> stream)
      : _sub = stream.listen(null) {
    _sub
      ..onData(_onData)
      ..onError(_onError)
      ..onDone(_onDone);
  }

  void _onData(List<int> chunk) {
    _buffer.addAll(chunk);
    _tryComplete();
  }

  void _tryComplete() {
    while (_pending.isNotEmpty) {
      final idx = _buffer.indexOf(10); // '\n'
      if (idx == -1) return;
      final lineBytes = _buffer.sublist(0, idx);
      _buffer.removeRange(0, idx + 1);
      _pending.removeAt(0).complete(utf8.decode(lineBytes));
    }
  }

  void _onError(Object e) {
    _error = e;
    for (final c in _pending) {
      if (!c.isCompleted) c.completeError(e);
    }
    _pending.clear();
  }

  void _onDone() {
    _error ??= const SocketException('Bağlantı karşı taraftan kapatıldı.');
    for (final c in _pending) {
      if (!c.isCompleted) c.completeError(_error!);
    }
    _pending.clear();
  }

  Future<String> readLine(Duration timeout) {
    final completer = Completer<String>();
    _pending.add(completer);
    _tryComplete();
    return completer.future.timeout(timeout);
  }

  Future<void> close() => _sub.cancel();
}

/// Hem "başka bir cihaz beni eşleştirsin/kontrol etsin" (host) hem de "ben
/// başka bir cihaza bağlanayım" (client) taraflarını yönetir.
class RemoteControlService {
  final Future<Map<String, dynamic>> Function() getConfig;
  final Future<void> Function(Map<String, dynamic> config) applyRemoteConfig;
  final Future<void> Function(String? sound) ringNow;
  final Future<void> Function() stopRinging;

  /// Eşleştirme isteği geldiğinde çağrılır - [decide] onay/red kararı ile
  /// çağrılmalıdır (senkron veya bir süre sonra asenkron olarak).
  final void Function(String requesterName, void Function(bool approved) decide)
      onPairingRequest;
  final void Function(String message) onLog;
  final String deviceName;
  final void Function()? onDevicesChanged;

  final List<PairedDevice> pairedDevices;

  RawDatagramSocket? _udpSocket;
  ServerSocket? _tcpServer;
  StreamSubscription<RawSocketEvent>? _udpSub;
  StreamSubscription<Socket>? _tcpSub;

  String? _activeCode;
  DateTime? _activeCodeExpiresAt;

  // Ayarları dışa aktarma kodu, eşleştirme kodundan tamamen ayrı bir
  // durumdur - eşleştirme kalıcı bir "uzaktan müdahale" ilişkisi kurarken,
  // bu sadece TEK SEFERLİK bir ayar kopyası gönderir, hiçbir token/kalıcı
  // kayıt oluşturmaz. Paylaşılacak config, kod üretilirken (generateExportCode)
  // anlık olarak "dondurulur".
  String? _activeExportCode;
  DateTime? _activeExportCodeExpiresAt;
  Map<String, dynamic>? _activeExportConfig;
  // UDP üzerinden kodu doğrulayıp "eşleşti" dedikten sonra, gerçek (büyük
  // olabilecek) ayar verisini güvenilir şekilde taşımak için karşı taraf
  // TCP ile bağlanır - bu harita UDP eşleşmesi ile TCP bağlantısı
  // arasındaki kısa pencerede kodun hâlâ geçerli olduğunu ve hangi config
  // anlık görüntüsüyle eşleştiğini izler.
  final Map<String, ({DateTime expiresAt, Map<String, dynamic> config})> _pendingExportGrants = {};

  RemoteControlService({
    required this.getConfig,
    required this.applyRemoteConfig,
    required this.ringNow,
    required this.stopRinging,
    required this.onPairingRequest,
    required this.onLog,
    required this.deviceName,
    this.onDevicesChanged,
    List<PairedDevice>? initialPairedDevices,
  }) : pairedDevices = List.of(initialPairedDevices ?? const []);

  // ---------- Yaşam döngüsü ----------
  Future<void> start() async {
    _udpSocket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, pairingUdpPort,
        reuseAddress: true, reusePort: false);
    _udpSocket!.broadcastEnabled = true;
    _udpSub = _udpSocket!.listen(_onUdpEvent);

    _tcpServer = await ServerSocket.bind(InternetAddress.anyIPv4, controlTcpPort,
        shared: true);
    _tcpSub = _tcpServer!.listen(_handleTcpConnection);
  }

  Future<void> stop() async {
    await _udpSub?.cancel();
    await _tcpSub?.cancel();
    _udpSocket?.close();
    await _tcpServer?.close();
  }

  // ---------- Host tarafı: eşleştirme kodu üretme ----------
  String generateCode() {
    _activeCode = generatePairingCode();
    _activeCodeExpiresAt = DateTime.now().add(const Duration(seconds: pairingCodeTtlSeconds));
    return _activeCode!;
  }

  void cancelCode() {
    _activeCode = null;
  }

  String? get _currentCode {
    if (_activeCode != null &&
        _activeCodeExpiresAt != null &&
        DateTime.now().isBefore(_activeCodeExpiresAt!)) {
      return _activeCode;
    }
    _activeCode = null;
    return null;
  }

  // ---------- Host tarafı: ayar dışa aktarma kodu üretme ----------
  /// [config]'in bir anlık görüntüsünü, üretilen kodu bilen ilk cihaza
  /// (tek seferlik) gönderilmek üzere "dondurur".
  String generateExportCode(Map<String, dynamic> config) {
    _activeExportCode = generatePairingCode();
    _activeExportCodeExpiresAt =
        DateTime.now().add(const Duration(seconds: configExportCodeTtlSeconds));
    _activeExportConfig = config;
    return _activeExportCode!;
  }

  void cancelExportCode() {
    _activeExportCode = null;
    _activeExportConfig = null;
  }

  String? get _currentExportCode {
    if (_activeExportCode != null &&
        _activeExportCodeExpiresAt != null &&
        DateTime.now().isBefore(_activeExportCodeExpiresAt!)) {
      return _activeExportCode;
    }
    _activeExportCode = null;
    _activeExportConfig = null;
    return null;
  }

  // ---------- UDP dinleme (keşif + eşleştirme) ----------
  void _onUdpEvent(RawSocketEvent event) {
    if (event != RawSocketEvent.read) return;
    final socket = _udpSocket;
    if (socket == null) return;
    final datagram = socket.receive();
    if (datagram == null) return;
    Map<String, dynamic> msg;
    try {
      msg = jsonDecode(utf8.decode(datagram.data)) as Map<String, dynamic>;
    } catch (_) {
      return;
    }
    try {
      _handleUdpMessage(msg, datagram.address, datagram.port);
    } catch (exc) {
      onLog('Eşleştirme mesajı işlenemedi: $exc');
    }
  }

  void _handleUdpMessage(Map<String, dynamic> msg, InternetAddress addr, int port) {
    final type = msg['type'];

    if (type == 'pair_request') {
      final code = _currentCode;
      if (code == null || msg['code'] != code) return; // bizim kodumuz değil
      final requesterName = (msg['name'] as String?) ?? 'Bilinmeyen Cihaz';
      // Kod, eşleşen İLK istekte hemen (onay beklenmeden) geçersiz kılınır -
      // aksi halde aynı kodla art arda/eşzamanlı gelen bir istek de eşleşip
      // ikinci bir onay isteği tetikleyebilir (kod tekrar kullanılmış olur).
      // Reddedilse bile kod bir daha kullanılamaz; yeni bir kod üretmek gerekir.
      _activeCode = null;
      _sendUdpTo({'v': protocolVersion, 'type': 'pair_ack'}, addr, port);

      var decided = false;
      void decide(bool approved) {
        if (decided) return;
        decided = true;
        if (approved) {
          final token = generateToken();
          final peer = PairedDevice(
              peerId: _generatePeerId(),
              name: requesterName,
              token: token,
              lastKnownIp: addr.address);
          pairedDevices.add(peer);
          onDevicesChanged?.call();
          _sendUdpTo({
            'v': protocolVersion,
            'type': 'pair_response',
            'approved': true,
            'host_name': deviceName,
            'token': token,
            'control_port': controlTcpPort,
          }, addr, port);
          onLog("'$requesterName' bu cihazla eşleşti (uzaktan müdahale açık).");
        } else {
          _sendUdpTo(
              {'v': protocolVersion, 'type': 'pair_response', 'approved': false}, addr, port);
        }
      }

      // Onay ekranını gösteren taraf (ör. UI isolate'i) kendi süresini
      // dolduramaz/gecikirse bile istek sonsuza kadar askıda kalmasın diye,
      // burada da bağımsız bir zaman aşımı koruması var.
      Timer(const Duration(seconds: approvalTimeoutSeconds), () => decide(false));
      onPairingRequest(requesterName, decide);
    } else if (type == 'locate_request') {
      final token = msg['token'];
      final hasMatch = pairedDevices.any((p) => p.token == token);
      if (hasMatch) {
        _sendUdpTo({
          'v': protocolVersion,
          'type': 'locate_response',
          'control_port': controlTcpPort,
          'host_name': deviceName,
        }, addr, port);
      }
    } else if (type == 'config_export_request') {
      final code = _currentExportCode;
      if (code == null || msg['code'] != code) return; // bizim kodumuz değil
      final requesterName = (msg['name'] as String?) ?? 'Bilinmeyen Cihaz';
      // Eşleştirme kodunda olduğu gibi, eşleşen İLK istekte kod hemen
      // geçersiz kılınır (tekrar kullanılamaz) - ama gerçek ayar verisini
      // (büyük olabileceğinden) güvenilir TCP üzerinden taşımak için, kısa
      // bir süre "bu kod bu TCP bağlantısı için geçerli" izni (kod
      // üretilirken dondurulan config anlık görüntüsüyle birlikte) bırakılır.
      _activeExportCode = null;
      final configSnapshot = _activeExportConfig;
      _activeExportConfig = null;
      if (configSnapshot != null) {
        _pendingExportGrants[code] = (
          expiresAt: DateTime.now().add(const Duration(seconds: configExportGrantTtlSeconds)),
          config: configSnapshot,
        );
      }
      _sendUdpTo({
        'v': protocolVersion,
        'type': 'config_export_ack',
        'control_port': controlTcpPort,
        'host_name': deviceName,
      }, addr, port);
      onLog("'$requesterName' bu cihazın ayarlarını dışa aktarma koduyla istedi.");
    }
  }

  void _sendUdpTo(Map<String, dynamic> payload, InternetAddress addr, int port) {
    final data = utf8.encode('${jsonEncode(payload)}\n');
    _udpSocket?.send(data, addr, port);
  }

  // ---------- Client tarafı: koda göre eşleştirme isteği gönder ----------
  /// Girilen kodu yerel ağa yayınlar, karşı taraf onaylarsa eşleşmiş cihaz
  /// kaydını döndürür. [onStatus] ile ara durumlar bildirilir.
  Future<PairedDevice?> pairWithCode(
      String code, void Function(String status) onStatus) async {
    final sock = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 0, reuseAddress: true);
    sock.broadcastEnabled = true;

    final request = {
      'v': protocolVersion,
      'type': 'pair_request',
      'code': code,
      'name': deviceName,
    };
    void broadcast() {
      final data = utf8.encode('${jsonEncode(request)}\n');
      sock.send(data, InternetAddress('255.255.255.255'), pairingUdpPort);
    }

    final completer = Completer<PairedDevice?>();
    var gotAck = false;
    Timer? rebroadcastTimer;
    Timer? timeoutTimer;
    late final StreamSubscription<RawSocketEvent> sub;

    void finish(PairedDevice? result) {
      rebroadcastTimer?.cancel();
      timeoutTimer?.cancel();
      sub.cancel();
      sock.close();
      if (!completer.isCompleted) completer.complete(result);
    }

    sub = sock.listen((event) {
      if (event != RawSocketEvent.read) return;
      final datagram = sock.receive();
      if (datagram == null) return;
      Map<String, dynamic> msg;
      try {
        msg = jsonDecode(utf8.decode(datagram.data)) as Map<String, dynamic>;
      } catch (_) {
        return;
      }
      if (msg['type'] == 'pair_ack' && !gotAck) {
        gotAck = true;
        onStatus('İstek gönderildi, karşı cihazda onay bekleniyor...');
        timeoutTimer?.cancel();
        timeoutTimer = Timer(const Duration(seconds: approvalTimeoutSeconds), () {
          onStatus('Zaman aşımı - onaylanmadı.');
          finish(null);
        });
      } else if (msg['type'] == 'pair_response') {
        if (msg['approved'] != true) {
          onStatus('Karşı cihaz isteği reddetti.');
          finish(null);
          return;
        }
        final peer = PairedDevice(
          peerId: _generatePeerId(),
          name: (msg['host_name'] as String?) ?? 'Bilinmeyen Cihaz',
          token: msg['token'] as String,
          lastKnownIp: datagram.address.address,
          controlPort: (msg['control_port'] as num?)?.toInt() ?? controlTcpPort,
        );
        pairedDevices.add(peer);
        onDevicesChanged?.call();
        onStatus("'${peer.name}' ile eşleşti.");
        finish(peer);
      }
    });

    broadcast();
    onStatus('Aranıyor...');
    rebroadcastTimer = Timer.periodic(const Duration(seconds: 2), (_) {
      if (!gotAck) broadcast();
    });
    timeoutTimer = Timer(const Duration(seconds: discoveryTimeoutSeconds), () {
      if (!gotAck) {
        onStatus('Zaman aşımı - kod bulunamadı ya da süresi doldu.');
        finish(null);
      }
    });

    return completer.future;
  }

  /// Girilen kodu yerel ağa yayınlar; karşı cihaz kodu tanırsa TÜM
  /// ayarlarını (kalıcı bir eşleştirme oluşturmadan, tek seferlik) geri
  /// gönderir. Başarılıysa (hostName, config) döner, aksi halde null.
  ///
  /// Eşleştirmedeki iki aşamalı desenin aynısı: önce UDP ile kodun eşleştiği
  /// doğrulanır (küçük, kayıp paketlere karşı tekrar gönderilen mesajlar),
  /// sonra gerçek (büyük olabilecek) ayar verisi güvenilir TCP üzerinden
  /// alınır.
  Future<(String, Map<String, dynamic>)?> requestConfigExport(
      String code, void Function(String status) onStatus) async {
    final sock = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 0, reuseAddress: true);
    sock.broadcastEnabled = true;

    final request = {
      'v': protocolVersion,
      'type': 'config_export_request',
      'code': code,
      'name': deviceName,
    };
    void broadcast() {
      final data = utf8.encode('${jsonEncode(request)}\n');
      sock.send(data, InternetAddress('255.255.255.255'), pairingUdpPort);
    }

    final completer = Completer<(String, Map<String, dynamic>)?>();
    var handled = false;
    Timer? rebroadcastTimer;
    Timer? timeoutTimer;
    late final StreamSubscription<RawSocketEvent> sub;

    void finish((String, Map<String, dynamic>)? result) {
      rebroadcastTimer?.cancel();
      timeoutTimer?.cancel();
      sub.cancel();
      sock.close();
      if (!completer.isCompleted) completer.complete(result);
    }

    sub = sock.listen((event) {
      if (event != RawSocketEvent.read) return;
      final datagram = sock.receive();
      if (datagram == null) return;
      Map<String, dynamic> msg;
      try {
        msg = jsonDecode(utf8.decode(datagram.data)) as Map<String, dynamic>;
      } catch (_) {
        return;
      }
      if (msg['type'] != 'config_export_ack' || handled) return;
      handled = true;
      onStatus('Kod bulundu, ayarlar alınıyor...');
      final ip = datagram.address.address;
      final controlPort = (msg['control_port'] as num?)?.toInt() ?? controlTcpPort;

      () async {
        try {
          final tcpSocket = await Socket.connect(ip, controlPort,
              timeout: const Duration(seconds: 10));
          final reader = _LineReader(tcpSocket);
          try {
            tcpSocket.add(utf8
                .encode('${jsonEncode({'type': 'export_config', 'code': code})}\n'));
            await tcpSocket.flush();
            final line = await reader.readLine(const Duration(seconds: 10));
            final result = jsonDecode(line) as Map<String, dynamic>;
            if (result['ok'] != true) {
              onStatus('Ayarlar alınamadı: ${result['error'] ?? 'bilinmeyen hata'}');
              finish(null);
              return;
            }
            final config = result['config'];
            if (config is! Map<String, dynamic>) {
              onStatus('Geçersiz yanıt alındı.');
              finish(null);
              return;
            }
            final hostName = (result['host_name'] as String?) ?? 'Bilinmeyen Cihaz';
            onStatus("'$hostName' cihazından ayarlar alındı.");
            finish((hostName, config));
          } finally {
            await reader.close();
            await tcpSocket.close();
          }
        } catch (exc) {
          onStatus('Ayarlar alınamadı: $exc');
          finish(null);
        }
      }();
    });

    broadcast();
    onStatus('Aranıyor...');
    rebroadcastTimer = Timer.periodic(const Duration(seconds: 2), (_) {
      if (!handled) broadcast();
    });
    timeoutTimer = Timer(const Duration(seconds: configExportDiscoveryTimeoutSeconds), () {
      if (!handled) {
        onStatus('Zaman aşımı - kod bulunamadı.');
        finish(null);
      }
    });

    return completer.future;
  }

  /// Eşleşmiş bir cihazın güncel IP'sini yeniden bulur (IP değişmiş olabilir).
  /// WiFi'de tek bir UDP yayın paketi kaybolabilir (sessizce düşer) - bu
  /// yüzden tek seferlik gönderim yerine, zaman aşımına kadar periyodik
  /// olarak tekrar gönderiyoruz (pairWithCode'daki yeniden gönderme
  /// deseniyle aynı) - aksi halde tek bir kayıp paket "cihaza
  /// ulaşılamadı" hatasına yol açabiliyordu.
  Future<String?> _locate(PairedDevice peer) async {
    final sock = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 0, reuseAddress: true);
    sock.broadcastEnabled = true;
    try {
      final request = {'v': protocolVersion, 'type': 'locate_request', 'token': peer.token};
      final data = utf8.encode('${jsonEncode(request)}\n');
      void broadcast() => sock.send(data, InternetAddress('255.255.255.255'), pairingUdpPort);

      final completer = Completer<String?>();
      Timer? timeoutTimer;
      Timer? resendTimer;
      late final StreamSubscription<RawSocketEvent> sub;

      void finish(String? result) {
        timeoutTimer?.cancel();
        resendTimer?.cancel();
        sub.cancel();
        if (!completer.isCompleted) completer.complete(result);
      }

      sub = sock.listen((event) {
        if (event != RawSocketEvent.read) return;
        final datagram = sock.receive();
        if (datagram == null) return;
        Map<String, dynamic> msg;
        try {
          msg = jsonDecode(utf8.decode(datagram.data)) as Map<String, dynamic>;
        } catch (_) {
          return;
        }
        if (msg['type'] == 'locate_response') {
          peer.controlPort = (msg['control_port'] as num?)?.toInt() ?? controlTcpPort;
          finish(datagram.address.address);
        }
      });

      broadcast();
      resendTimer = Timer.periodic(const Duration(seconds: 1), (_) => broadcast());
      timeoutTimer = Timer(const Duration(seconds: locateTimeoutSeconds), () => finish(null));

      final result = await completer.future;
      if (result != null) peer.lastKnownIp = result;
      return result;
    } finally {
      sock.close();
    }
  }

  // ---------- Client tarafı: uzak cihaza komut gönderme ----------
  /// Eşleşmiş bir cihaza tek bir komut gönderip yanıtını döndürür.
  /// Bağlanılamazsa cihazı yeniden bulmayı (locate) bir kez dener.
  Future<Map<String, dynamic>> sendCommand(PairedDevice peer, Map<String, dynamic> cmd,
      {Duration timeout = const Duration(seconds: 8)}) async {
    Object? lastError;
    for (var attempt = 0; attempt < 2; attempt++) {
      var ip = peer.lastKnownIp;
      if (ip == null || attempt == 1) {
        ip = await _locate(peer);
        if (ip == null) {
          lastError = 'Cihaz ağda bulunamadı.';
          continue;
        }
      }
      try {
        return await _sendCommandTo(ip, peer.controlPort, peer.token, cmd, timeout);
      } catch (exc) {
        lastError = exc;
        peer.lastKnownIp = null;
      }
    }
    throw Exception(lastError?.toString() ?? 'Bağlanılamadı.');
  }

  Future<Map<String, dynamic>> _sendCommandTo(String ip, int port, String token,
      Map<String, dynamic> cmd, Duration timeout) async {
    final socket = await Socket.connect(ip, port, timeout: timeout);
    final reader = _LineReader(socket);
    try {
      socket.add(utf8.encode('${jsonEncode({'type': 'auth', 'token': token})}\n'));
      await socket.flush();
      final authLine = await reader.readLine(timeout);
      final authResult = jsonDecode(authLine) as Map<String, dynamic>;
      if (authResult['ok'] != true) {
        throw Exception('Kimlik doğrulama reddedildi (eşleştirme kaldırılmış olabilir).');
      }
      socket.add(utf8.encode('${jsonEncode({'type': 'cmd', ...cmd})}\n'));
      await socket.flush();
      final resultLine = await reader.readLine(timeout);
      return jsonDecode(resultLine) as Map<String, dynamic>;
    } finally {
      await reader.close();
      await socket.close();
    }
  }

  // ---------- Host tarafı: TCP komut sunucusu ----------
  void _handleTcpConnection(Socket socket) {
    () async {
      final reader = _LineReader(socket);
      try {
        final authLine = await reader.readLine(const Duration(seconds: 30));
        final authMsg = jsonDecode(authLine) as Map<String, dynamic>;
        if (authMsg['type'] == 'export_config') {
          await _handleExportConfigTcp(socket, authMsg);
          return;
        }
        if (authMsg['type'] != 'auth') return;
        final token = authMsg['token'];
        final matches = pairedDevices.where((p) => p.token == token).toList();
        if (matches.isEmpty) {
          socket.add(utf8.encode('${jsonEncode({'ok': false})}\n'));
          await socket.flush();
          return;
        }
        final peer = matches.first;
        peer.lastKnownIp = socket.remoteAddress.address;
        socket.add(utf8.encode('${jsonEncode({'ok': true})}\n'));
        await socket.flush();

        final cmdLine = await reader.readLine(const Duration(seconds: 30));
        final cmdMsg = jsonDecode(cmdLine) as Map<String, dynamic>;
        final result = await _executeCommand(cmdMsg, peer);
        socket.add(utf8.encode('${jsonEncode(result)}\n'));
        await socket.flush();
      } catch (exc) {
        onLog('Uzaktan müdahale bağlantı hatası: $exc');
      } finally {
        await reader.close();
        await socket.close();
      }
    }();
  }

  /// UDP aşamasında kodu doğrulayıp geçici bir izin bırakmıştık (bkz.
  /// _handleUdpMessage'daki 'config_export_request') - burada o izni
  /// tüketip gerçek ayar verisini gönderiyoruz. Kalıcı bir token/eşleşme
  /// oluşturulmaz; bu tamamen tek seferlik bir işlemdir.
  Future<void> _handleExportConfigTcp(Socket socket, Map<String, dynamic> msg) async {
    final code = msg['code'] as String?;
    final grant = code != null ? _pendingExportGrants.remove(code) : null;
    if (grant == null || DateTime.now().isAfter(grant.expiresAt)) {
      socket.add(utf8
          .encode('${jsonEncode({'ok': false, 'error': 'Kod geçersiz ya da süresi dolmuş.'})}\n'));
      await socket.flush();
      return;
    }
    socket.add(utf8.encode(
        '${jsonEncode({'ok': true, 'config': grant.config, 'host_name': deviceName})}\n'));
    await socket.flush();
    onLog('Ayarlar dışa aktarma koduyla başka bir cihaza gönderildi.');
  }

  Future<Map<String, dynamic>> _executeCommand(
      Map<String, dynamic> msg, PairedDevice peer) async {
    final cmd = msg['cmd'];
    try {
      switch (cmd) {
        case 'ring_now':
          await ringNow(msg['sound'] as String?);
          onLog("'${peer.name}' zili şimdi çaldırdı (uzaktan müdahale).");
          await recordRing("Uzaktan Zil ('${peer.name}')", 'remote');
          return {'ok': true};
        case 'fire_button':
          // 'ring_now' (sound=null) bu cihazın VARSAYILAN sesini çalar -
          // yangın butonuna özel sesi değil. Karşı cihazın kendi
          // fire_button_sound'unu okuyup çalıyoruz, tıpkı o cihazda
          // fiziksel yangın butonuna basılmış gibi.
          final cfg = await getConfig();
          await ringNow(cfg['fire_button_sound'] as String?);
          onLog("'${peer.name}' yangın butonunu uzaktan tetikledi.");
          await recordRing("Uzaktan Yangın Butonu ('${peer.name}')", 'remote_fire_button');
          return {'ok': true};
        case 'stop':
          await stopRinging();
          return {'ok': true};
        case 'get_config':
          return {'ok': true, 'data': await getConfig()};
        case 'set_config':
          final newCfg = msg['config'];
          if (newCfg is! Map<String, dynamic>) {
            return {'ok': false, 'error': 'Geçersiz ayar verisi.'};
          }
          await applyRemoteConfig(newCfg);
          onLog("'${peer.name}' ayarları uzaktan değiştirdi.");
          return {'ok': true};
        case 'unpair':
          // Karşı taraf eşleştirmeyi kendi tarafında kaldırdı - biz de
          // kaldırıyoruz, aksi halde bu taraf artık geçersiz/ölü bir
          // eşleştirmeyi göstermeye devam eder (kullanınca "kimlik
          // doğrulama reddedildi" hatası alır ama listeden hiç temizlenmez).
          pairedDevices.removeWhere((p) => p.token == peer.token);
          onDevicesChanged?.call();
          onLog("'${peer.name}' eşleştirmeyi kaldırdı.");
          return {'ok': true};
        default:
          return {'ok': false, 'error': 'Bilinmeyen komut: $cmd'};
      }
    } catch (exc) {
      return {'ok': false, 'error': exc.toString()};
    }
  }

  void removePairedDevice(String peerId) {
    final peer = pairedDevices.where((p) => p.peerId == peerId).firstOrNull;
    pairedDevices.removeWhere((p) => p.peerId == peerId);
    onDevicesChanged?.call();
    if (peer != null) {
      // Karşı tarafa da haber ver ki orada da otomatik temizlensin - iyi
      // niyetli (best-effort) bir bildirimdir: karşı cihaz kapalıysa/ağda
      // değilse sessizce başarısız olur, yerel kaldırma zaten tamamlanmıştır.
      sendCommand(peer, {'cmd': 'unpair'}, timeout: const Duration(seconds: 4))
          .catchError((_) => <String, dynamic>{});
    }
  }
}

extension _FirstOrNullExtension<T> on Iterable<T> {
  T? get firstOrNull => isEmpty ? null : first;
}
