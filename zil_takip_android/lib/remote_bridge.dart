// Ana arayüz (UI) isolate'i ile arka plan servisi isolate'i arasında,
// FlutterBackgroundService'in mevcut invoke/on olay kanalı üzerinden
// uzaktan müdahale komutlarını (ör. "zili çal", "ayarları getir") istek
// kimliğiyle (request_id) eşleştirip Future'a çeviren köprü.
import 'dart:async';

import 'package:flutter_background_service/flutter_background_service.dart';

import 'models.dart';

class RemoteCommandBridge {
  final Map<String, Completer<Map<String, dynamic>>> _pending = {};
  StreamSubscription<Map<String, dynamic>?>? _sub;

  RemoteCommandBridge() {
    try {
      _sub = FlutterBackgroundService().on('remote_command_result').listen((event) {
        final requestId = event?['request_id'] as String?;
        if (requestId == null) return;
        final completer = _pending.remove(requestId);
        if (completer == null || completer.isCompleted) return;
        final error = event?['error'];
        if (error != null) {
          completer.completeError(Exception(error.toString()));
          return;
        }
        final result = event?['result'];
        completer.complete(
            result is Map ? Map<String, dynamic>.from(result) : <String, dynamic>{});
      });
    } catch (_) {
      // Arka plan servisi bu platformda/ortamda kullanılamıyor olabilir.
    }
  }

  Future<Map<String, dynamic>> send(String peerId, Map<String, dynamic> cmd,
      {Duration timeout = const Duration(seconds: 12)}) {
    final requestId = uuid.v4();
    final completer = Completer<Map<String, dynamic>>();
    _pending[requestId] = completer;
    try {
      FlutterBackgroundService()
          .invoke('remote_command', {'request_id': requestId, 'peer_id': peerId, 'cmd': cmd});
    } catch (exc) {
      _pending.remove(requestId);
      return Future.error(exc);
    }
    return completer.future.timeout(timeout, onTimeout: () {
      _pending.remove(requestId);
      throw TimeoutException('Uzak cihaza ulaşılamadı (zaman aşımı).');
    });
  }

  void dispose() {
    _sub?.cancel();
  }
}
