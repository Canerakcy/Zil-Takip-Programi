// "Namaz Vakitleri" sekmesi - günlük vakit sesleri (basit aç/kapa + ses) ve
// ayrı, esnek çoklu-girdili Cuma Namazı bölümü. Windows sürümündeki
// _build_prayer_tab()'ın karşılığı.
import 'package:flutter/material.dart';

import 'dialogs.dart';
import 'models.dart';
import 'prayer_service.dart';

class PrayerTab extends StatefulWidget {
  final AppConfig config;
  final VoidCallback onChanged;
  final void Function(String? sound) onTest;

  const PrayerTab({
    super.key,
    required this.config,
    required this.onChanged,
    required this.onTest,
  });

  @override
  State<PrayerTab> createState() => _PrayerTabState();
}

class _PrayerTabState extends State<PrayerTab> {
  late final TextEditingController _cityController;
  late final TextEditingController _countryController;

  Map<String, String>? _timings;
  bool _loadingTimings = false;
  String? _timingsStatus;

  PrayerTimesConfig get _pt => widget.config.prayerTimes;

  @override
  void initState() {
    super.initState();
    _cityController = TextEditingController(text: _pt.city);
    _countryController = TextEditingController(text: _pt.country);
    if (_pt.city.trim().isNotEmpty) _fetchTimings();
  }

  @override
  void dispose() {
    _cityController.dispose();
    _countryController.dispose();
    super.dispose();
  }

  Future<void> _fetchTimings() async {
    final city = _pt.city.trim();
    final country = _pt.country.trim();
    if (city.isEmpty) {
      setState(() {
        _timings = null;
        _timingsStatus = 'Önce bir şehir girin.';
      });
      return;
    }
    setState(() {
      _loadingTimings = true;
      _timingsStatus = null;
    });
    try {
      final (timings, fromNetwork) =
          await getCachedOrFetchDay(city, country, DateTime.now());
      if (!mounted) return;
      setState(() {
        _timings = timings;
        _loadingTimings = false;
        _timingsStatus = timings == null
            ? '$city için vakitler alınamadı - internet bağlantısını kontrol edin.'
            : (fromNetwork
                ? '$city için bugünün vakitleri internetten alındı.'
                : '$city için önbellekteki vakitler gösteriliyor (internet yok).');
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _timings = null;
        _loadingTimings = false;
        _timingsStatus = '$city için vakitler alınamadı - internet bağlantısını kontrol edin.';
      });
    }
  }

  void _commitLocation() {
    final cityChanged = _pt.city != _cityController.text.trim();
    final countryChanged = _pt.country != _countryController.text.trim();
    _pt.city = _cityController.text.trim();
    _pt.country = _countryController.text.trim();
    widget.onChanged();
    if (cityChanged || countryChanged) _fetchTimings();
  }

  Future<void> _pickVakitSound(String vakit) async {
    final path = await pickSoundFile();
    if (path == null) return;
    setState(() => _pt.daily[vakit]!.sound = path);
    widget.onChanged();
  }

  Future<void> _addFridayOffset() async {
    final offset = await showFridayOffsetDialog(context);
    if (offset == null) return;
    setState(() => _pt.fridayOffsets.add(offset));
    widget.onChanged();
  }

  Future<void> _editFridayOffset(FridayOffset offset) async {
    final updated = await showFridayOffsetDialog(context, existing: offset);
    if (updated == null) return;
    final index = _pt.fridayOffsets.indexWhere((o) => o.id == offset.id);
    if (index != -1) setState(() => _pt.fridayOffsets[index] = updated);
    widget.onChanged();
  }

  void _deleteFridayOffset(FridayOffset offset) {
    showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Zili Sil'),
        content:
            const Text('Bu Cuma namazı zilini silmek istediğinize emin misiniz?'),
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
        setState(() => _pt.fridayOffsets.removeWhere((o) => o.id == offset.id));
        widget.onChanged();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final ogle = _timings?['ogle'];
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Namaz Vakitlerini Kullan'),
          value: _pt.enabled,
          onChanged: (value) {
            setState(() => _pt.enabled = value);
            widget.onChanged();
          },
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _cityController,
                decoration: const InputDecoration(labelText: 'Şehir'),
                onSubmitted: (_) => _commitLocation(),
                onTapOutside: (_) => _commitLocation(),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: TextField(
                controller: _countryController,
                decoration: const InputDecoration(labelText: 'Ülke'),
                onSubmitted: (_) => _commitLocation(),
                onTapOutside: (_) => _commitLocation(),
              ),
            ),
            IconButton(
              icon: _loadingTimings
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.refresh),
              tooltip: 'Bugünün Vakitlerini Göster',
              onPressed: _loadingTimings
                  ? null
                  : () {
                      _commitLocation();
                      _fetchTimings();
                    },
            ),
          ],
        ),
        if (_timingsStatus != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              _timingsStatus!,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        const SizedBox(height: 24),
        Text('Günlük Vakit Sesi', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Card(
          child: Column(
            children: [
              for (final vakit in vakitKeys)
                ListTile(
                  title: Row(
                    children: [
                      Text(vakitLabels[vakit]!),
                      const SizedBox(width: 8),
                      Text(
                        _timings?[vakit] ?? '--:--',
                        style: Theme.of(context)
                            .textTheme
                            .bodyMedium
                            ?.copyWith(fontWeight: FontWeight.bold),
                      ),
                    ],
                  ),
                  subtitle: Text(soundDisplayName(_pt.daily[vakit]!.sound)),
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      IconButton(
                        icon: const Icon(Icons.audiotrack),
                        tooltip: 'Ses Seç',
                        onPressed: () => _pickVakitSound(vakit),
                      ),
                      IconButton(
                        icon: const Icon(Icons.volume_up),
                        tooltip: 'Test Et',
                        onPressed: () => widget.onTest(_pt.daily[vakit]!.sound),
                      ),
                      Switch(
                        value: _pt.daily[vakit]!.enabled,
                        onChanged: (value) {
                          setState(() => _pt.daily[vakit]!.enabled = value);
                          widget.onChanged();
                        },
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: 24),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('Cuma Namazı', style: Theme.of(context).textTheme.titleMedium),
            IconButton(
              icon: const Icon(Icons.add_circle_outline),
              tooltip: 'Yeni Cuma Namazı Zili Ekle',
              onPressed: _addFridayOffset,
            ),
          ],
        ),
        if (ogle != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Text(
              'Bugün öğle vakti: $ogle - Cuma namazı zilleri bu saate göre hesaplanır.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        if (_pt.fridayOffsets.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 8),
            child: Text('Henüz Cuma namazı zili eklenmedi.'),
          ),
        for (final offset in _pt.fridayOffsets)
          Card(
            child: ListTile(
              leading: Switch(
                value: offset.enabled,
                onChanged: (value) {
                  setState(() => offset.enabled = value);
                  widget.onChanged();
                },
              ),
              title: Text(offset.label.isNotEmpty
                  ? offset.label
                  : 'Cuma Namazı - ${offset.minutes} dk ${offset.direction == 'before' ? 'kala' : 'sonra'}'),
              subtitle: Text(ogle != null
                  ? '${soundDisplayName(offset.sound)} • Çalma saati: ${applyOffsetMinutes(ogle, offset.direction == 'after' ? offset.minutes : -offset.minutes)}'
                  : soundDisplayName(offset.sound)),
              onTap: () => _editFridayOffset(offset),
              trailing: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  IconButton(
                    icon: const Icon(Icons.volume_up),
                    tooltip: 'Test Et',
                    onPressed: () => widget.onTest(offset.sound),
                  ),
                  IconButton(
                    icon: const Icon(Icons.delete_outline),
                    tooltip: 'Sil',
                    onPressed: () => _deleteFridayOffset(offset),
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }
}
