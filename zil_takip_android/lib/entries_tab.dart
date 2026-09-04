// "Zil Programı" sekmesi - Windows sürümündeki entries ağacının karşılığı.
import 'package:flutter/material.dart';

import 'dialogs.dart';
import 'models.dart';

class EntriesTab extends StatelessWidget {
  final AppConfig config;
  final VoidCallback onChanged;
  final void Function(String? sound) onTest;

  const EntriesTab({
    super.key,
    required this.config,
    required this.onChanged,
    required this.onTest,
  });

  Future<void> _addEntry(BuildContext context) async {
    final entry = await showBellEntryDialog(context);
    if (entry == null) return;
    config.entries.add(entry);
    onChanged();
  }

  Future<void> _editEntry(BuildContext context, BellEntry entry) async {
    final updated = await showBellEntryDialog(context, existing: entry);
    if (updated == null) return;
    final index = config.entries.indexWhere((e) => e.id == entry.id);
    if (index != -1) config.entries[index] = updated;
    onChanged();
  }

  void _deleteEntry(BuildContext context, BellEntry entry) {
    showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Zili Sil'),
        content:
            Text('"${entry.label}" zilini silmek istediğinize emin misiniz?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Vazgeç'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Sil'),
          ),
        ],
      ),
    ).then((confirmed) {
      if (confirmed == true) {
        config.entries.removeWhere((e) => e.id == entry.id);
        onChanged();
      }
    });
  }

  String _daysText(List<int> days) {
    if (days.length == 7) return 'Her gün';
    final sorted = [...days]..sort();
    return sorted.map((d) => dayShort[d]).join(', ');
  }

  @override
  Widget build(BuildContext context) {
    final entries = config.entries;
    return Scaffold(
      body: entries.isEmpty
          ? const Center(
              child: Text(
                'Henüz zil eklenmedi.\nSağ alttaki + ile ekleyin.',
                textAlign: TextAlign.center,
              ),
            )
          : ListView.builder(
              padding: const EdgeInsets.symmetric(vertical: 8),
              itemCount: entries.length,
              itemBuilder: (context, index) {
                final entry = entries[index];
                return Card(
                  margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  child: ListTile(
                    leading: Switch(
                      value: entry.enabled,
                      onChanged: (value) {
                        entry.enabled = value;
                        onChanged();
                      },
                    ),
                    title: Text(entry.label),
                    subtitle: Text('${entry.time} • ${_daysText(entry.days)}'),
                    onTap: () => _editEntry(context, entry),
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        IconButton(
                          icon: const Icon(Icons.volume_up),
                          tooltip: 'Test Et',
                          onPressed: () => onTest(entry.sound),
                        ),
                        IconButton(
                          icon: const Icon(Icons.delete_outline),
                          tooltip: 'Sil',
                          onPressed: () => _deleteEntry(context, entry),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _addEntry(context),
        tooltip: 'Yeni Zil Ekle',
        child: const Icon(Icons.add),
      ),
    );
  }
}
