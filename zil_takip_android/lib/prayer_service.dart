// Seçilen il/ilçe için günlük namaz vakitlerini internetten çekip
// önbellekleyen modül - Windows sürümündeki prayer_service.py'nin karşılığı.
// Diyanet İşleri Başkanlığı hesaplama yöntemiyle (method=13) Aladhan API
// kullanılır: https://aladhan.com/prayer-times-api
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:intl/intl.dart';

import 'config_store.dart';

const String aladhanUrl = 'https://api.aladhan.com/v1/timingsByCity';
const int diyanetMethod = 13;
const String cacheFileName = 'vakit_cache.json';

const Map<String, String> vakitToAladhanKey = {
  'imsak': 'Imsak',
  'gunes': 'Sunrise',
  'ogle': 'Dhuhr',
  'ikindi': 'Asr',
  'aksam': 'Maghrib',
  'yatsi': 'Isha',
};

String _cleanHhmm(String value) {
  // API bazen "13:12 (+03)" gibi bölge bilgisi ekleyebiliyor.
  return value.split(' ')[0].trim();
}

Future<File> _cacheFile() async {
  final dir = await getAppDataDir();
  return File('${dir.path}/$cacheFileName');
}

Future<Map<String, dynamic>> _loadCache() async {
  final file = await _cacheFile();
  if (!await file.exists()) return {};
  try {
    final content = await file.readAsString();
    return jsonDecode(content) as Map<String, dynamic>;
  } catch (_) {
    return {};
  }
}

Future<void> _saveCache(Map<String, dynamic> cache) async {
  try {
    final file = await _cacheFile();
    await file.writeAsString(jsonEncode(cache));
  } catch (_) {
    // Önbellek yazılamasa da vakitler o an için elde, uygulama çalışmaya devam eder.
  }
}

/// Verilen tarih/şehir için tüm vakitleri {"imsak": "HH:MM", ...} şeklinde
/// döndürür. Başarısız olursa istisna fırlatır.
Future<Map<String, String>> fetchDayTimings(
    DateTime date, String city, String country) async {
  final dateStr = DateFormat('dd-MM-yyyy').format(date);
  final uri = Uri.parse(aladhanUrl).replace(queryParameters: {
    'city': city,
    'country': country,
    'method': diyanetMethod.toString(),
    'date': dateStr,
  });
  final response = await http.get(uri).timeout(const Duration(seconds: 10));
  if (response.statusCode != 200) {
    throw Exception('Aladhan API hata döndürdü: ${response.statusCode}');
  }
  final body = jsonDecode(response.body) as Map<String, dynamic>;
  final timings = (body['data'] as Map<String, dynamic>)['timings']
      as Map<String, dynamic>;
  return {
    for (final entry in vakitToAladhanKey.entries)
      entry.key: _cleanHhmm(timings[entry.value] as String),
  };
}

/// (vakitler, internetten_mi_alindi) döndürür. İnternet yoksa ve önbellekte
/// aynı tarih/şehir için kayıt varsa onu döndürür.
Future<(Map<String, String>?, bool)> getCachedOrFetchDay(
    String city, String country, DateTime targetDate) async {
  final dateKey =
      '${targetDate.year.toString().padLeft(4, '0')}-${targetDate.month.toString().padLeft(2, '0')}-${targetDate.day.toString().padLeft(2, '0')}';
  final cacheKey = '$country|$city|$dateKey';
  final cache = await _loadCache();

  try {
    final timings = await fetchDayTimings(targetDate, city, country);
    cache[cacheKey] = timings;
    await _saveCache(cache);
    return (timings, true);
  } catch (_) {
    final cached = cache[cacheKey] as Map<String, dynamic>?;
    if (cached == null) return (null, false);
    return (cached.map((key, value) => MapEntry(key, value as String)), false);
  }
}

/// Bir vakte, işaretli (pozitif/negatif) dakika ekler - Cuma namazı
/// önce/sonra kayıtları için kullanılır.
String applyOffsetMinutes(String hhmm, int minutes) {
  final parts = hhmm.split(':');
  final base = DateTime(2000, 1, 1, int.parse(parts[0]), int.parse(parts[1]));
  final result = base.add(Duration(minutes: minutes));
  return '${result.hour.toString().padLeft(2, '0')}:${result.minute.toString().padLeft(2, '0')}';
}
