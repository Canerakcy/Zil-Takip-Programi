// "Genel" sekmesi - varsayılan ses, ses seviyesi, telefon açılınca otomatik
// başlatma, tatil günleri ve kayıt (log) görünümü. Windows sürümündeki
// _build_general_tab()/_build_audio_tab()'ın karşılığı.
import 'dart:convert';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';

import 'background_service.dart';
import 'dialogs.dart';
import 'models.dart';

class GeneralTab extends StatefulWidget {
  final AppConfig config;
  final VoidCallback onChanged;
  final List<String> logLines;

  /// Ayarları JSON dosyasına kaydetme (yedekleme) - widget.config'in
  /// KENDİSİ (yerel modda bu telefonun, uzak modda eşleşmiş cihazın son
  /// çekilen ayarları) dışa aktarılır, bu yüzden ayrı bir callback
  /// gerekmez.
  ///
  /// İçe aktarma ise TÜM ayarların yerini alan yepyeni bir AppConfig nesnesi
  /// üretir - widget.config'i mutasyona uğratmak yerine (StatefulWidget'lar
  /// arasında referans paylaşımı kırılgan olurdu) çağırana bu yeni nesneyi
  /// TESLİM EDİYORUZ; çağıran (HomePage: yerelde kaydet, RemoteSettingsPage:
  /// eşleşmiş cihaza gönder) neyle ne yapacağını bilir.
  final Future<void> Function(AppConfig imported) onImportConfig;

  /// Bu sekme, eşleşmiş UZAK bir cihazın ayarlarını göstermek için mi
  /// kullanılıyor (bkz. RemoteSettingsPage)? Telefon açılınca otomatik
  /// başlatma ve pil optimizasyonu muafiyeti Android izin/servis
  /// çağrılarını HER ZAMAN bu widget'ı ÇALIŞTIRAN (yani kontrol eden)
  /// telefonda tetikler - uzak bir cihazın ayarlarını görüntülerken bunlar
  /// yanlışlıkla kontrol eden telefonu etkiler (izin isteği açar/otomatik
  /// başlatmayı değiştirir). Bu yüzden uzak modda bu bölüm tamamen
  /// gizlenir.
  final bool isRemote;

  const GeneralTab({
    super.key,
    required this.config,
    required this.onChanged,
    required this.logLines,
    required this.onImportConfig,
    this.isRemote = false,
  });

  @override
  State<GeneralTab> createState() => _GeneralTabState();
}

class _GeneralTabState extends State<GeneralTab> {
  bool? _batteryOptimizationIgnored;

  @override
  void initState() {
    super.initState();
    if (!widget.isRemote) {
      _refreshBatteryOptimizationStatus();
    }
  }

  Future<void> _refreshBatteryOptimizationStatus() async {
    try {
      final status = await Permission.ignoreBatteryOptimizations.status;
      if (mounted) setState(() => _batteryOptimizationIgnored = status.isGranted);
    } catch (_) {
      // Bu platformda/ortamda desteklenmiyor olabilir.
    }
  }

  Future<void> _requestBatteryOptimizationExemption() async {
    try {
      await Permission.ignoreBatteryOptimizations.request();
    } catch (_) {
      // Bu platformda/ortamda desteklenmiyor olabilir.
    }
    await _refreshBatteryOptimizationStatus();
  }

  Future<void> _pickDefaultSound() async {
    final path = await pickSoundFile();
    if (path == null) return;
    setState(() => widget.config.defaultSound = path);
    widget.onChanged();
  }

  void _clearDefaultSound() {
    setState(() => widget.config.defaultSound = null);
    widget.onChanged();
  }

  Future<void> _exportConfig() async {
    final jsonStr = const JsonEncoder.withIndent('  ').convert(widget.config.toJson());
    try {
      final savedPath = await FilePicker.saveFile(
        dialogTitle: 'Ayarları Dışa Aktar',
        fileName: 'zil_takip_ayarlari.json',
        type: FileType.custom,
        allowedExtensions: ['json'],
        bytes: utf8.encode(jsonStr),
      );
      if (!mounted || savedPath == null) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Ayarlar dışa aktarıldı.')));
    } catch (exc) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Dışa aktarılamadı: $exc')));
    }
  }

  Future<void> _importConfig() async {
    final result =
        await FilePicker.pickFiles(type: FileType.custom, allowedExtensions: ['json']);
    final path = result?.files.single.path;
    if (path == null) return;

    Map<String, dynamic> data;
    try {
      final content = await File(path).readAsString();
      data = jsonDecode(content) as Map<String, dynamic>;
    } catch (exc) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Dosya okunamadı ya da geçersiz: $exc')));
      return;
    }

    if (!mounted) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Ayarları İçe Aktar'),
        content: const Text(
            'Bu, mevcut TÜM ayarların (zil kayıtları, namaz vakitleri, tatil günleri, '
            'sesler) üzerine yazacak. Devam edilsin mi?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Vazgeç')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('İçe Aktar')),
        ],
      ),
    );
    if (confirmed != true) return;

    AppConfig imported;
    try {
      imported = AppConfig.fromJson(data);
    } catch (exc) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Geçersiz ayar dosyası: $exc')));
      return;
    }
    await widget.onImportConfig(imported);
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(const SnackBar(content: Text('Ayarlar içe aktarıldı.')));
  }

  Future<void> _addHoliday() async {
    final holiday = await showHolidayDialog(context);
    if (holiday == null) return;
    setState(() => widget.config.holidays.add(holiday));
    widget.onChanged();
  }

  Future<void> _editHoliday(Holiday holiday) async {
    final updated = await showHolidayDialog(context, existing: holiday);
    if (updated == null) return;
    final index = widget.config.holidays.indexOf(holiday);
    if (index != -1) setState(() => widget.config.holidays[index] = updated);
    widget.onChanged();
  }

  void _deleteHoliday(Holiday holiday) {
    setState(() => widget.config.holidays.remove(holiday));
    widget.onChanged();
  }

  Future<void> _pickFireButtonSound() async {
    final path = await pickSoundFile();
    if (path == null) return;
    setState(() => widget.config.fireButtonSound = path);
    widget.onChanged();
  }

  void _clearFireButtonSound() {
    setState(() => widget.config.fireButtonSound = null);
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
        if (widget.isRemote)
          Padding(
            padding: const EdgeInsets.only(bottom: 16),
            child: Text(
              'Not: Bir ses dosyası seçerseniz, seçtiğiniz dosya BU telefondadır - '
              'eşleşmiş cihaz o dosyaya erişemeyebilir. Ses dosyalarını mümkünse '
              'doğrudan ilgili cihazın kendisinde ayarlayın.',
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: Colors.orange[800]),
            ),
          ),
        Text('Ses Ayarları', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Card(
          child: Column(
            children: [
              ListTile(
                title: const Text('Varsayılan Ses'),
                subtitle: Text(soundDisplayName(config.defaultSound)),
                trailing: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (config.defaultSound != null && config.defaultSound!.isNotEmpty)
                      IconButton(
                        icon: const Icon(Icons.clear),
                        tooltip: 'Kaldır',
                        onPressed: _clearDefaultSound,
                      ),
                    const Icon(Icons.audiotrack),
                  ],
                ),
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
        if (!widget.isRemote) ...[
          const SizedBox(height: 24),
          Text('Genel Ayarlar', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Card(
            child: Column(
              children: [
                SwitchListTile(
                  title: const Text('Telefon Açılınca Otomatik Başlat'),
                  subtitle: const Text(
                      'Cihaz yeniden başlatıldığında servis otomatik başlar.'),
                  value: config.startOnBoot,
                  onChanged: (value) {
                    setState(() => config.startOnBoot = value);
                    widget.onChanged();
                    initializeBackgroundService(autoStartOnBoot: value);
                  },
                ),
                const Divider(height: 1),
                ListTile(
                  title: const Text('Pil Optimizasyonundan Muaf Tut'),
                  subtitle: Text(_batteryOptimizationIgnored == true
                      ? 'Etkin - Android arka plan servisini kapatmayacak.'
                      : 'Kapalı - bazı telefonlarda (ör. Samsung) servis bir '
                          'süre sonra durdurulabilir, açmanız önerilir.'),
                  trailing: _batteryOptimizationIgnored == true
                      ? const Icon(Icons.check_circle, color: Colors.green)
                      : FilledButton(
                          onPressed: _requestBatteryOptimizationExemption,
                          child: const Text('Aç'),
                        ),
                ),
              ],
            ),
          ),
        ] else ...[
          const SizedBox(height: 24),
          Text(
            'Telefon açılınca otomatik başlatma ve pil optimizasyonu muafiyeti gibi bu '
            'cihaza özgü ayarlar burada gösterilmez - bunlar yalnızca eşleşmiş cihazın '
            'kendisinde değiştirilebilir.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
        const SizedBox(height: 24),
        Text('Ayarları Yedekle / Geri Yükle', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _exportConfig,
                    icon: const Icon(Icons.upload_file),
                    label: const Text('Dışa Aktar'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _importConfig,
                    icon: const Icon(Icons.download_outlined),
                    label: const Text('İçe Aktar'),
                  ),
                ),
              ],
            ),
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
              subtitle: Text(holiday.ring
                  ? '${holiday.date} • Özel zil: ${holiday.ringTime ?? '--:--'} '
                      '(${soundDisplayName(holiday.ringSound)})'
                  : holiday.date),
              onTap: () => _editHoliday(holiday),
              trailing: IconButton(
                icon: const Icon(Icons.delete_outline),
                tooltip: 'Sil',
                onPressed: () => _deleteHoliday(holiday),
              ),
            ),
          ),
        const SizedBox(height: 24),
        Text('Yangın Butonu', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Card(
          child: ListTile(
            leading: const Icon(Icons.local_fire_department, color: Colors.red),
            title: const Text('Yangın Butonu Sesi'),
            subtitle: Text(soundDisplayName(config.fireButtonSound)),
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (config.fireButtonSound != null && config.fireButtonSound!.isNotEmpty)
                  IconButton(
                    icon: const Icon(Icons.clear),
                    tooltip: 'Kaldır',
                    onPressed: _clearFireButtonSound,
                  ),
                const Icon(Icons.audiotrack),
              ],
            ),
            onTap: _pickFireButtonSound,
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
