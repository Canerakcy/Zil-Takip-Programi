// "İstatistikler" sekmesi - zil çalma geçmişi ve basit özet sayılar
// (bugün/bu hafta/bu ay) - Windows sürümündeki App._build_stats_tab()'ın
// karşılığı.
import 'package:flutter/material.dart';

import 'ring_history.dart';

const Map<String, String> ringKindLabels = {
  'entry': 'Zil Programı',
  'prayer': 'Namaz Vakti',
  'friday': 'Cuma Namazı',
  'holiday': 'Tatil Günü',
  'fire_button': 'Yangın Butonu',
  'remote': 'Uzaktan Zil',
  'remote_fire_button': 'Uzaktan Yangın Butonu',
};

String _formatRingTime(DateTime t) {
  String two(int n) => n.toString().padLeft(2, '0');
  return '${two(t.day)}.${two(t.month)}.${t.year} '
      '${two(t.hour)}:${two(t.minute)}:${two(t.second)}';
}

class StatsTab extends StatefulWidget {
  const StatsTab({super.key});

  @override
  State<StatsTab> createState() => _StatsTabState();
}

class _StatsTabState extends State<StatsTab> {
  List<RingHistoryEntry> _entries = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final entries = await loadRingHistory();
    entries.sort((a, b) => b.time.compareTo(a.time));
    if (!mounted) return;
    setState(() {
      _entries = entries;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final weekStart = today.subtract(Duration(days: now.weekday - 1));
    final monthStart = DateTime(now.year, now.month, 1);

    var todayCount = 0;
    var weekCount = 0;
    var monthCount = 0;
    for (final entry in _entries) {
      final d = DateTime(entry.time.year, entry.time.month, entry.time.day);
      if (!d.isBefore(today)) todayCount++;
      if (!d.isBefore(weekStart)) weekCount++;
      if (!d.isBefore(monthStart)) monthCount++;
    }

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: _loading
            ? const [
                SizedBox(height: 220),
                Center(child: CircularProgressIndicator()),
              ]
            : [
                Row(
                  children: [
                    Expanded(child: _StatCard(title: 'Bugün', count: todayCount)),
                    const SizedBox(width: 12),
                    Expanded(child: _StatCard(title: 'Bu Hafta', count: weekCount)),
                    const SizedBox(width: 12),
                    Expanded(child: _StatCard(title: 'Bu Ay', count: monthCount)),
                  ],
                ),
                const SizedBox(height: 24),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('Son Zil Kayıtları', style: Theme.of(context).textTheme.titleMedium),
                    IconButton(
                      icon: const Icon(Icons.refresh),
                      tooltip: 'Yenile',
                      onPressed: _load,
                    ),
                  ],
                ),
                if (_entries.isEmpty)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 16),
                    child: Text('Henüz zil çalma kaydı yok.'),
                  ),
                for (final entry in _entries.take(300))
                  Card(
                    child: ListTile(
                      leading: Icon(
                        entry.success ? Icons.check_circle : Icons.error,
                        color: entry.success ? Colors.green : Colors.red,
                      ),
                      title: Text(entry.label),
                      subtitle: Text(
                          '${ringKindLabels[entry.kind] ?? entry.kind} • '
                          '${_formatRingTime(entry.time)}'
                          '${entry.success ? '' : ' • ${entry.error ?? 'Hata'}'}'),
                    ),
                  ),
              ],
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  final String title;
  final int count;

  const _StatCard({required this.title, required this.count});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 16),
        child: Column(
          children: [
            Text('$count',
                style: Theme.of(context)
                    .textTheme
                    .headlineMedium
                    ?.copyWith(fontWeight: FontWeight.bold)),
            const SizedBox(height: 4),
            Text(title, style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}
