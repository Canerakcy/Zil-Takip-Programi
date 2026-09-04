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
    return AppConfig.fromJson(json);
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
