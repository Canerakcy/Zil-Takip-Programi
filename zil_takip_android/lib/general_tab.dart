// "Genel" sekmesi - varsayılan ses, ses seviyesi, telefon açılınca otomatik
// başlatma, tatil günleri ve kayıt (log) görünümü. Windows sürümündeki
// _build_general_tab()/_build_audio_tab()'ın karşılığı.
import 'package:flutter/material.dart';

import 'background_service.dart';
import 'dialogs.dart';
import 'models.dart';

class GeneralTab extends StatefulWidget {
  final AppConfig config;
  final VoidCallback onChanged;
  final List<String> logLines;

  const GeneralTab({
    super.key,
    required this.config,
    required this.onChanged,
    required this.logLines,
  });

  @override
  State<GeneralTab> createState() => _GeneralTabState();
}

class _GeneralTabState extends State<GeneralTab> {
  Future<void> _pickDefaultSound() async {
    final path = await pickSoundFile();
    if (path == null) return;
    setState(() => widget.config.defaultSound = path);
    widget.onChanged();
  }

  Future<void> _addHoliday() async {
    final holiday = await showHolidayDialog(context);
    if (holiday == null) return;
    setState(() => widget.config.holidays.add(holiday));
    widget.onChanged();
  }

  void _deleteHoliday(Holiday holiday) {
    setState(() => widget.config.holidays.remove(holiday));
    widget.onChanged();
  }

  @override
  Widget build(BuildContext context) {
    final config = widget.config;
    final sortedHolidays = [...config.holidays]
      ..sort((a, b) => a.date.compareTo(b.date));

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Ses Ayarları', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Card(
          child: Column(
            children: [
              ListTile(
                title: const Text('Varsayılan Ses'),
                subtitle: Text(soundDisplayName(config.defaultSound)),
                trailing: const Icon(Icons.audiotrack),
                onTap: _pickDefaultSound,
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                child: Row(
                  children: [
                    const Icon(Icons.volume_down),
                    Expanded(
                      child: Slider(
                        value: config.volume.clamp(0.0, 1.0),
                        onChanged: (value) {
                          setState(() => config.volume = value);
                        },
                        onChangeEnd: (value) {
                          config.volume = value;
                          widget.onChanged();
                        },
                      ),
                    ),
                    const Icon(Icons.volume_up),
                  ],
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 24),
        Text('Genel Ayarlar', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Card(
          child: SwitchListTile(
            title: const Text('Telefon Açılınca Otomatik Başlat'),
            subtitle:
                const Text('Cihaz yeniden başlatıldığında servis otomatik başlar.'),
            value: config.startOnBoot,
            onChanged: (value) {
              setState(() => config.startOnBoot = value);
              widget.onChanged();
              initializeBackgroundService(autoStartOnBoot: value);
            },
          ),
        ),
        const SizedBox(height: 24),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('Tatil Günleri', style: Theme.of(context).textTheme.titleMedium),
            IconButton(
              icon: const Icon(Icons.add_circle_outline),
              tooltip: 'Tatil Günü Ekle',
              onPressed: _addHoliday,
            ),
          ],
        ),
        if (sortedHolidays.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 8),
            child: Text('Henüz tatil günü eklenmedi.'),
          ),
        for (final holiday in sortedHolidays)
          Card(
            child: ListTile(
              title: Text(holiday.label.isNotEmpty ? holiday.label : 'Tatil'),
              subtitle: Text(holiday.date),
              trailing: IconButton(
                icon: const Icon(Icons.delete_outline),
                tooltip: 'Sil',
                onPressed: () => _deleteHoliday(holiday),
              ),
            ),
          ),
        const SizedBox(height: 24),
        Text('Kayıtlar', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Card(
          child: SizedBox(
            height: 220,
            child: Padding(
              padding: const EdgeInsets.all(8),
              child: widget.logLines.isEmpty
                  ? const Center(child: Text('Henüz kayıt yok.'))
                  : ListView.builder(
                      itemCount: widget.logLines.length,
                      itemBuilder: (context, index) => Padding(
                        padding: const EdgeInsets.symmetric(vertical: 2),
                        child: Text(
                          widget.logLines[index],
                          style:
                              const TextStyle(fontFamily: 'monospace', fontSize: 12),
                        ),
                      ),
                    ),
            ),
          ),
        ),
      ],
    );
  }
}
