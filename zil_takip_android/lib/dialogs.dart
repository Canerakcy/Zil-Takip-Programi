// Zil, Cuma namazı zili ve tatil günü ekleme/düzenleme diyalogları -
// Windows sürümündeki EntryDialog/FridayOffsetDialog/HolidayDialog'un
// karşılığı.
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import 'models.dart';

Future<String?> pickSoundFile() async {
  final files = await FilePicker.pickFiles(type: FileType.audio);
  if (files.isEmpty) return null;
  return files.single.path;
}

String soundDisplayName(String? sound) {
  if (sound == null || sound.isEmpty || sound == 'default') {
    return 'Varsayılan ses';
  }
  return sound.split('/').last;
}

Future<BellEntry?> showBellEntryDialog(BuildContext context,
    {BellEntry? existing}) {
  return showDialog<BellEntry>(
    context: context,
    builder: (_) => _BellEntryDialog(existing: existing),
  );
}

class _BellEntryDialog extends StatefulWidget {
  final BellEntry? existing;
  const _BellEntryDialog({this.existing});

  @override
  State<_BellEntryDialog> createState() => _BellEntryDialogState();
}

class _BellEntryDialogState extends State<_BellEntryDialog> {
  late final TextEditingController _labelController;
  late TimeOfDay _time;
  late Set<int> _days;
  String? _sound;
  late bool _enabled;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    _labelController = TextEditingController(text: e?.label ?? '');
    if (e != null) {
      final parts = e.time.split(':');
      _time =
          TimeOfDay(hour: int.parse(parts[0]), minute: int.parse(parts[1]));
    } else {
      _time = const TimeOfDay(hour: 8, minute: 0);
    }
    _days = (e?.days ?? const [0, 1, 2, 3, 4]).toSet();
    _sound = e?.sound;
    _enabled = e?.enabled ?? true;
  }

  @override
  void dispose() {
    _labelController.dispose();
    super.dispose();
  }

  Future<void> _pickTime() async {
    final picked = await showTimePicker(context: context, initialTime: _time);
    if (picked != null) setState(() => _time = picked);
  }

  Future<void> _pickSound() async {
    final path = await pickSoundFile();
    if (path != null) setState(() => _sound = path);
  }

  String get _timeText =>
      '${_time.hour.toString().padLeft(2, '0')}:${_time.minute.toString().padLeft(2, '0')}';

  void _save() {
    final label = _labelController.text.trim();
    if (label.isEmpty || _days.isEmpty) return;
    final result = BellEntry(
      id: widget.existing?.id ?? uuid.v4(),
      label: label,
      time: _timeText,
      days: _days.toList()..sort(),
      sound: _sound,
      enabled: _enabled,
    );
    Navigator.pop(context, result);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.existing == null ? 'Yeni Zil' : 'Zili Düzenle'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            TextField(
              controller: _labelController,
              decoration: const InputDecoration(labelText: 'Etiket'),
            ),
            const SizedBox(height: 16),
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Saat'),
              subtitle: Text(_timeText),
              trailing: const Icon(Icons.access_time),
              onTap: _pickTime,
            ),
            const SizedBox(height: 8),
            const Text('Günler', style: TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            Wrap(
              spacing: 6,
              children: List.generate(7, (i) {
                final selected = _days.contains(i);
                return FilterChip(
                  label: Text(dayShort[i]),
                  selected: selected,
                  onSelected: (value) {
                    setState(() {
                      if (value) {
                        _days.add(i);
                      } else {
                        _days.remove(i);
                      }
                    });
                  },
                );
              }),
            ),
            const SizedBox(height: 16),
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Ses'),
              subtitle: Text(soundDisplayName(_sound)),
              trailing: const Icon(Icons.audiotrack),
              onTap: _pickSound,
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Etkin'),
              value: _enabled,
              onChanged: (value) => setState(() => _enabled = value),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Vazgeç'),
        ),
        FilledButton(onPressed: _save, child: const Text('Kaydet')),
      ],
    );
  }
}

Future<FridayOffset?> showFridayOffsetDialog(BuildContext context,
    {FridayOffset? existing}) {
  return showDialog<FridayOffset>(
    context: context,
    builder: (_) => _FridayOffsetDialog(existing: existing),
  );
}

class _FridayOffsetDialog extends StatefulWidget {
  final FridayOffset? existing;
  const _FridayOffsetDialog({this.existing});

  @override
  State<_FridayOffsetDialog> createState() => _FridayOffsetDialogState();
}

class _FridayOffsetDialogState extends State<_FridayOffsetDialog> {
  late final TextEditingController _minutesController;
  late final TextEditingController _labelController;
  late String _direction;
  String? _sound;
  late bool _enabled;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    _minutesController =
        TextEditingController(text: (e?.minutes ?? 15).toString());
    _labelController = TextEditingController(text: e?.label ?? '');
    _direction = e?.direction ?? 'before';
    _sound = e?.sound;
    _enabled = e?.enabled ?? true;
  }

  @override
  void dispose() {
    _minutesController.dispose();
    _labelController.dispose();
    super.dispose();
  }

  Future<void> _pickSound() async {
    final path = await pickSoundFile();
    if (path != null) setState(() => _sound = path);
  }

  void _save() {
    final minutes = int.tryParse(_minutesController.text.trim());
    if (minutes == null || minutes <= 0) return;
    final result = FridayOffset(
      id: widget.existing?.id ?? uuid.v4(),
      minutes: minutes,
      direction: _direction,
      label: _labelController.text.trim(),
      sound: _sound,
      enabled: _enabled,
    );
    Navigator.pop(context, result);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.existing == null
          ? 'Yeni Cuma Namazı Zili'
          : 'Cuma Namazı Zilini Düzenle'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            TextField(
              controller: _labelController,
              decoration:
                  const InputDecoration(labelText: 'Etiket (boş bırakılabilir)'),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _minutesController,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Dakika'),
            ),
            const SizedBox(height: 16),
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(
                    value: 'before', label: Text('Öğleden Önce (Kala)')),
                ButtonSegment(value: 'after', label: Text('Öğleden Sonra')),
              ],
              selected: {_direction},
              onSelectionChanged: (value) =>
                  setState(() => _direction = value.first),
            ),
            const SizedBox(height: 16),
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Ses'),
              subtitle: Text(soundDisplayName(_sound)),
              trailing: const Icon(Icons.audiotrack),
              onTap: _pickSound,
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Etkin'),
              value: _enabled,
              onChanged: (value) => setState(() => _enabled = value),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Vazgeç'),
        ),
        FilledButton(onPressed: _save, child: const Text('Kaydet')),
      ],
    );
  }
}

Future<Holiday?> showHolidayDialog(BuildContext context, {Holiday? existing}) {
  return showDialog<Holiday>(
    context: context,
    builder: (_) => _HolidayDialog(existing: existing),
  );
}

class _HolidayDialog extends StatefulWidget {
  final Holiday? existing;
  const _HolidayDialog({this.existing});

  @override
  State<_HolidayDialog> createState() => _HolidayDialogState();
}

class _HolidayDialogState extends State<_HolidayDialog> {
  late final TextEditingController _labelController;
  DateTime? _date;

  @override
  void initState() {
    super.initState();
    _labelController =
        TextEditingController(text: widget.existing?.label ?? '');
    final existingDate = widget.existing?.date;
    _date = existingDate != null ? DateTime.tryParse(existingDate) : null;
  }

  @override
  void dispose() {
    _labelController.dispose();
    super.dispose();
  }

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _date ?? now,
      firstDate: DateTime(now.year - 1),
      lastDate: DateTime(now.year + 5),
    );
    if (picked != null) setState(() => _date = picked);
  }

  void _save() {
    final date = _date;
    if (date == null) return;
    final dateStr =
        '${date.year.toString().padLeft(4, '0')}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';
    Navigator.pop(
        context, Holiday(date: dateStr, label: _labelController.text.trim()));
  }

  @override
  Widget build(BuildContext context) {
    final date = _date;
    return AlertDialog(
      title:
          Text(widget.existing == null ? 'Yeni Tatil Günü' : 'Tatil Gününü Düzenle'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Tarih'),
            subtitle: Text(date == null
                ? 'Seçilmedi'
                : '${date.day.toString().padLeft(2, '0')}.${date.month.toString().padLeft(2, '0')}.${date.year}'),
            trailing: const Icon(Icons.calendar_today),
            onTap: _pickDate,
          ),
          TextField(
            controller: _labelController,
            decoration: const InputDecoration(labelText: 'Açıklama (ör. Bayram)'),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Vazgeç'),
        ),
        FilledButton(onPressed: _save, child: const Text('Kaydet')),
      ],
    );
  }
}
