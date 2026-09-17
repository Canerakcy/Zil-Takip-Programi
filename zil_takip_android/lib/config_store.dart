// Ayarların diske (uygulamanın kendi belgeler klasörüne) JSON olarak
// kaydedilip okunmasından sorumlu - Windows sürümündeki config_store.py'nin
// karşılığı. Atomik yazım için önce ".tmp" dosyasına yazılır, sonra asıl
// dosyanın üzerine taşınır (yarım kalmış bir yazım yüzünden bozuk config
// oluşmasını önler).
import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

import 'models.dart';

const String configFileName = 'config.json';
const String pairedDevicesFileName = 'paired_devices.json';

Future<Directory> getAppDataDir() async {
  final dir = await getApplicationDocumentsDirectory();
  return dir;
}

Future<File> getConfigFile() async {
  final dir = await getAppDataDir();
  return File('${dir.path}/$configFileName');
}

Future<AppConfig> loadConfig() async {
  final file = await getConfigFile();
  if (!await file.exists()) {
    final config = AppConfig.createDefault();
    await saveConfig(config);
    return config;
  }
  try {
    final content = await file.readAsString();
    final json = jsonDecode(content) as Map<String, dynamic>;
    final config = AppConfig.fromJson(json);
    if (await _migrateLegacySoundPaths(config)) {
      await saveConfig(config);
    }
    return config;
  } catch (_) {
    final config = AppConfig.createDefault();
    await saveConfig(config);
    return config;
  }
}

Future<void> saveConfig(AppConfig config) async {
  final file = await getConfigFile();
  final tmpFile = File('${file.path}.tmp');
  final content = const JsonEncoder.withIndent('  ').convert(config.toJson());
  await tmpFile.writeAsString(content, flush: true);
  await tmpFile.rename(file.path);
}

/// Bir ses dosyasını uygulamanın kalıcı belgeler klasörü altındaki
/// "sounds/(benzersiz-klasör)/(orijinal-ad)" konumuna kopyalar ve yeni yolu
/// döndürür. Her kopya kendi klasörüne konur ki aynı isimli iki farklı
/// dosya (ör. iki ayrı kayıt için seçilen iki farklı "zil.mp3") birbirinin
/// üzerine yazılmasın; dosya adı yine de korunur (bkz. dialogs.dart
/// soundDisplayName - yolun son parçasını gösterir).
Future<String> copySoundToPersistentStorage(
    String sourcePath, String fileName) async {
  final dir = await getAppDataDir();
  final destDir = Directory('${dir.path}/sounds/${uuid.v4()}');
  await destDir.create(recursive: true);
  final destPath = '${destDir.path}/$fileName';
  await File(sourcePath).copy(destPath);
  return destPath;
}

/// pickSoundFile() (dialogs.dart) eskiden file_picker'ın Android'de
/// döndürdüğü geçici ÖNBELLEK (cache) yolunu doğrudan kaydediyordu - bu
/// klasör Android tarafından (depolama azaldığında ya da kullanıcı
/// "Önbelleği Temizle" dediğinde) herhangi bir an otomatik boşaltılabilir,
/// bu da zil çalarken sessizce/"setDataSource failed" hatasıyla
/// başarısız olmaya yol açar. Bu düzeltmeden önce seçilmiş, hâlâ diskte
/// okunabilir olan eski ses yolları burada sessizce kalıcı depolamaya
/// (copySoundToPersistentStorage) taşınır - kullanıcının hiçbir şey
/// yapmasına gerek kalmadan, bir sonraki açılışta mevcut (henüz
/// kaybolmamış) seçimler kalıcı hale gelir. Dosya zaten kaybolmuşsa
/// yapılacak bir şey yoktur, olduğu gibi bırakılır - zil çalarken zaten
/// "Ses çalınamadı" olarak raporlanır (bkz. audio_player_service.dart).
///
/// Zaten kalıcı "sounds/" klasöründeki yollar için hiçbir dosya G/Ç'si
/// yapılmadan (yalnızca ucuz bir metin öneki kontrolüyle) hemen çıkılır -
/// bu yüzden ilk (tek seferlik) taşımadan sonraki her loadConfig()
/// çağrısının maliyeti neredeyse sıfırdır.
Future<bool> _migrateLegacySoundPaths(AppConfig config) async {
  final dir = await getAppDataDir();
  final soundsPrefix = '${dir.path}/sounds/';
  var changed = false;

  Future<String?> migrate(String? path) async {
    if (path == null || path.isEmpty || path == 'default') return path;
    if (path.startsWith(soundsPrefix)) return path;
    // Bu blok kasıtlı olarak geniş bir try/catch içinde: burada oluşacak
    // herhangi bir hata (ör. exists() izin hatası), yakalanmazsa loadConfig()
    // içindeki genel catch'e düşüp kullanıcının TÜM config'ini varsayılana
    // sıfırlardı - bir taşıma denemesi yüzünden ayarların kaybolmaması için
    // burada yutulup orijinal yol değiştirilmeden döndürülür.
    try {
      if (!await File(path).exists()) return path;
      final fileName = path.split('/').last;
      final newPath = await copySoundToPersistentStorage(path, fileName);
      changed = true;
      return newPath;
    } catch (_) {
      return path;
    }
  }

  config.defaultSound = await migrate(config.defaultSound);
  config.fireButtonSound = await migrate(config.fireButtonSound);
  for (final entry in config.entries) {
    entry.sound = await migrate(entry.sound);
  }
  for (final vakit in vakitKeys) {
    final setting = config.prayerTimes.daily[vakit];
    if (setting != null) setting.sound = await migrate(setting.sound);
  }
  for (final offset in config.prayerTimes.fridayOffsets) {
    offset.sound = await migrate(offset.sound);
  }
  for (final holiday in config.holidays) {
    holiday.ringSound = await migrate(holiday.ringSound);
  }

  return changed;
}

Future<File> getPairedDevicesFile() async {
  final dir = await getAppDataDir();
  return File('${dir.path}/$pairedDevicesFileName');
}

Future<List<Map<String, dynamic>>> loadPairedDevicesRaw() async {
  final file = await getPairedDevicesFile();
  if (!await file.exists()) return [];
  try {
    final content = await file.readAsString();
    final decoded = jsonDecode(content);
    if (decoded is! List) return [];
    return decoded.cast<Map<String, dynamic>>();
  } catch (_) {
    return [];
  }
}

Future<void> savePairedDevicesRaw(List<Map<String, dynamic>> devices) async {
  final file = await getPairedDevicesFile();
  final tmpFile = File('${file.path}.tmp');
  await tmpFile.writeAsString(jsonEncode(devices), flush: true);
  await tmpFile.rename(file.path);
}
