// Zil sesi çalma - Windows sürümündeki audio_player.py'nin karşılığı.
// Android'de tek sistem çıkışı olduğundan (Windows'taki gibi cihaz seçimi
// yok), sadece dosya yolu ve ses seviyesi yeterlidir.
import 'package:audioplayers/audioplayers.dart';

class AudioPlayerService {
  final AudioPlayer _player = AudioPlayer();

  /// [soundPath] null/boş ya da "default" ise [defaultSound] çalınır.
  /// İkisi de yoksa hiçbir şey çalmaz (kullanıcı henüz ses seçmemiştir).
  Future<void> playFile(
      String? soundPath, String? defaultSound, double volume) async {
    final path = (soundPath == null || soundPath.isEmpty || soundPath == 'default')
        ? defaultSound
        : soundPath;
    if (path == null || path.isEmpty) return;
    await _player.setVolume(volume.clamp(0.0, 1.0));
    await _player.play(DeviceFileSource(path));
  }

  Future<void> dispose() async {
    await _player.dispose();
  }
}
