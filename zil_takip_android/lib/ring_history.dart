// Zil çalma geçmişini (istatistikler için) diske kaydeden/okuyan yardımcı -
// Windows sürümündeki ring_history.py'nin karşılığı. JSON Lines (.jsonl)
// formatında: her satır bağımsız bir olay, dosya sonuna eklenir. Uygulama
// yıllarca kapatılmadan çalışabileceği için dosya sınırsız büyümesin diye
// belirli bir boyutu aşınca en son N kayda kırpılır.
import 'dart:convert';
import 'dart:io';

import 'config_store.dart';

const String ringHistoryFileName = 'ring_history.jsonl';
const int maxRingHistoryEntries = 5000;
const int ringHistoryTrimCheckBytes = 5 * 1024 * 1024;

class RingHistoryEntry {
  final DateTime time;
  final String label;
  final String kind;
  final bool success;
  final String? error;

  RingHistoryEntry({
    required this.time,
    required this.label,
    required this.kind,
    this.success = true,
    this.error,
  });

  Map<String, dynamic> toJson() => {
        'time': time.toIso8601String(),
        'label': label,
        'kind': kind,
        'success': success,
        if (error != null) 'error': error,
      };

  factory RingHistoryEntry.fromJson(Map<String, dynamic> json) => RingHistoryEntry(
        time: DateTime.tryParse(json['time'] as String? ?? '') ?? DateTime.now(),
        label: json['label'] as String? ?? '',
        kind: json['kind'] as String? ?? '',
        success: json['success'] as bool? ?? true,
        error: json['error'] as String?,
      );
}

Future<File> getRingHistoryFile() async {
  final dir = await getAppDataDir();
  return File('${dir.path}/$ringHistoryFileName');
}

/// Bir zil çalma olayını kalıcı geçmişe ekler (İstatistikler sekmesinde
/// gösterilir). Bu asla zilin çalmasını engellememeli/geciktirmemeli -
/// yazma hatası sessizce yutulur.
Future<void> recordRing(String label, String kind, {bool success = true, String? error}) async {
  try {
    final file = await getRingHistoryFile();
    final entry = RingHistoryEntry(
        time: DateTime.now(), label: label, kind: kind, success: success, error: error);
    await file.writeAsString('${jsonEncode(entry.toJson())}\n',
        mode: FileMode.append, flush: true);
    await _trimIfNeeded(file);
  } catch (_) {
    // Geçmiş kaydı başarısız olsa bile zilin çalması engellenmemeli.
  }
}

Future<void> _trimIfNeeded(File file) async {
  try {
    final stat = await file.stat();
    if (stat.size < ringHistoryTrimCheckBytes) return;
    final lines = await file.readAsLines();
    if (lines.length <= maxRingHistoryEntries) return;
    final trimmed = lines.sublist(lines.length - maxRingHistoryEntries);
    final tmpFile = File('${file.path}.tmp');
    await tmpFile.writeAsString('${trimmed.join('\n')}\n', flush: true);
    await tmpFile.rename(file.path);
  } catch (_) {
    // Kırpma başarısız olursa dosya büyümeye devam eder - kritik değil.
  }
}

/// Tüm geçmişi (en eskiden en yeniye) döndürür - dosya yoksa/okunamazsa
/// boş liste döner.
Future<List<RingHistoryEntry>> loadRingHistory() async {
  try {
    final file = await getRingHistoryFile();
    if (!await file.exists()) return [];
    final lines = await file.readAsLines();
    final entries = <RingHistoryEntry>[];
    for (final line in lines) {
      if (line.trim().isEmpty) continue;
      try {
        entries.add(RingHistoryEntry.fromJson(jsonDecode(line) as Map<String, dynamic>));
      } catch (_) {
        // bozuk satır - atla
      }
    }
    return entries;
  } catch (_) {
    return [];
  }
}
