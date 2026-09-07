// Zil sesi çalma - Windows sürümündeki audio_player.py'nin karşılığı.
// Android'de tek sistem çıkışı olduğundan (Windows'taki gibi cihaz seçimi
// yok), sadece dosya yolu ve ses seviyesi yeterlidir.
import 'dart:async';

import 'package:audioplayers/audioplayers.dart';

class AudioPlayerService {
  final AudioPlayer _player = AudioPlayer();
  StreamSubscription<void>? _eventSub;

  /// Ses dosyası native tarafta (ör. cihazın medya çözücüsü) oynatılamazsa
  /// bu hata yalnızca olay kanalı (event channel) üzerinden asenkron olarak
  /// gelir - play() Future'ı bunu hiç yakalamaz. Bu yüzden ayrıca dinlenip
  /// [onError] ile dışarı bildirilir; aksi halde "hiçbir hata yok ama ses de
  /// gelmiyor" şeklinde sessizce başarısız olur.
  AudioPlayerService({void Function(String message)? onError}) {
    if (onError != null) {
      _eventSub = _player.eventStream.listen(
        (_) {},
        onError: (Object error, StackTrace _) {
          onError('Ses çalınamadı: $error');
        },
      );
    }
  }

  /// [soundPath] null/boş ya da "default" ise [defaultSound] çalınır.
  /// İkisi de yoksa hiçbir şey çalmaz (kullanıcı henüz ses seçmemiştir) ve
  /// `false` döner - çağıran taraf bunu kullanıcıya bildirebilir.
  Future<bool> playFile(
      String? soundPath, String? defaultSound, double volume) async {
    final path = (soundPath == null || soundPath.isEmpty || soundPath == 'default')
        ? defaultSound
        : soundPath;
    if (path == null || path.isEmpty) return false;
    await _player.setVolume(volume.clamp(0.0, 1.0));
    await _player.play(DeviceFileSource(path));
    return true;
  }

  Future<void> dispose() async {
    await _eventSub?.cancel();
    await _player.dispose();
  }
}
