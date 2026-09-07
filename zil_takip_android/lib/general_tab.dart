// "Genel" sekmesi - varsayılan ses, ses seviyesi, telefon açılınca otomatik
// başlatma, tatil günleri ve kayıt (log) görünümü. Windows sürümündeki
// _build_general_tab()/_build_audio_tab()'ın karşılığı.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:permission_handler/permission_handler.dart';

import 'background_service.dart';
import 'dialogs.dart';
import 'models.dart';

class GeneralTab extends StatefulWidget {
  final AppConfig config;
  final VoidCallback onChanged;
  final List<String> logLines;

  /// Ayarları bir kod üreterek dışa aktarma (Uzaktan Erişim sekmesindeki
  /// eşleştirme koduyla aynı mekanizma) - widget.config'in KENDİSİ (yerel
  /// modda bu telefonun, uzak modda eşleşmiş cihazın son çekilen ayarları)
  /// paylaşılır, bu yüzden ayrı bir callback gerekmez.
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
    await showDialog<void>(
      context: context,
      builder: (_) => _ExportCodeDialog(config: widget.config.toJson()),
    );
  }

  Future<void> _importConfig() async {
    final result = await showDialog<(String, Map<String, dynamic>)>(
      context: context,
      builder: (_) => const _ImportCodeDialog(),
    );
    if (result == null) return;
    final (hostName, configJson) = result;

    if (!mounted) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Ayarları İçe Aktar'),
        content: Text(
            "'$hostName' cihazından alınan ayarlar, mevcut TÜM ayarların (zil kayıtları, "
            'namaz vakitleri, tatil günleri, sesler) üzerine yazacak. Devam edilsin mi?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Vazgeç')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('İçe Aktar')),
        ],
      ),
    );
    if (confirmed != true) return;

    AppConfig imported;
    try {
      imported = AppConfig.fromJson(configJson);
    } catch (exc) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Geçersiz ayar verisi: $exc')));
      return;
    }
    await widget.onImportConfig(imported);
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text("Ayarlar '$hostName' cihazından içe aktarıldı.")));
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
        Text('Ayarları Kod ile Aktar', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _exportConfig,
                    icon: const Icon(Icons.vpn_key),
                    label: const Text('Kod Oluştur'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _importConfig,
                    icon: const Icon(Icons.download_outlined),
                    label: const Text('Kod ile İçe Aktar'),
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

/// Ayarları dışa aktarmak için bir kod üretip gösteren diyalog - tıpkı
/// "Uzaktan Erişim" sekmesindeki eşleştirme koduna benziyor, ama kalıcı bir
/// ilişki kurmaz: yalnızca kodu bilen İLK cihaza, üretim anındaki ayarların
/// TEK SEFERLİK bir kopyasını gönderir. Kod üretimi/iptali arka plan
/// servisindeki RemoteControlService üzerinden (FlutterBackgroundService
/// invoke/on kanalıyla) yürütülür.
class _ExportCodeDialog extends StatefulWidget {
  final Map<String, dynamic> config;

  const _ExportCodeDialog({required this.config});

  @override
  State<_ExportCodeDialog> createState() => _ExportCodeDialogState();
}

class _ExportCodeDialogState extends State<_ExportCodeDialog> {
  String? _code;
  StreamSubscription<Map<String, dynamic>?>? _sub;

  @override
  void initState() {
    super.initState();
    try {
      _sub = FlutterBackgroundService().on('export_code').listen((event) {
        final code = event?['code'] as String?;
        if (mounted && code != null) setState(() => _code = code);
      });
      FlutterBackgroundService()
          .invoke('generate_export_code', {'config': widget.config});
    } catch (_) {
      // Arka plan servisi bu platformda/ortamda kullanılamıyor olabilir.
    }
  }

  @override
  void dispose() {
    _sub?.cancel();
    try {
      FlutterBackgroundService().invoke('cancel_export_code');
    } catch (_) {
      // Arka plan servisi bu platformda/ortamda kullanılamıyor olabilir.
    }
    super.dispose();
  }

  Future<void> _copyCode() async {
    final code = _code;
    if (code == null) return;
    await Clipboard.setData(ClipboardData(text: code));
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(const SnackBar(content: Text('Kod kopyalandı.')));
  }

  @override
  Widget build(BuildContext context) {
    final code = _code;
    return AlertDialog(
      title: const Text('Ayarları Dışa Aktar'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Bu kodu, ayarları almak istediğiniz cihazda "Kod ile İçe Aktar" '
              'ekranına girin. Yalnızca aynı yerel ağda (WiFi) çalışır.'),
          const SizedBox(height: 16),
          if (code == null)
            const Center(child: Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: CircularProgressIndicator(),
            ))
          else
            Row(
              children: [
                Expanded(
                  child: SelectableText(
                    code,
                    style: const TextStyle(
                        fontSize: 24, fontWeight: FontWeight.bold, letterSpacing: 1),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.copy),
                  tooltip: 'Kopyala',
                  onPressed: _copyCode,
                ),
              ],
            ),
          const SizedBox(height: 8),
          Text(
            '5 dakika içinde girilmezse ya da bir kez kullanılınca bu kod geçersiz olur.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Kapat')),
      ],
    );
  }
}

/// Bir cihazda gösterilen dışa aktarma kodunu girip o cihazın ayarlarını
/// almak için kullanılan diyalog. Başarılıysa (hostName, config) ile
/// Navigator.pop edilir.
class _ImportCodeDialog extends StatefulWidget {
  const _ImportCodeDialog();

  @override
  State<_ImportCodeDialog> createState() => _ImportCodeDialogState();
}

class _ImportCodeDialogState extends State<_ImportCodeDialog> {
  final TextEditingController _codeController = TextEditingController();
  StreamSubscription<Map<String, dynamic>?>? _statusSub;
  StreamSubscription<Map<String, dynamic>?>? _resultSub;
  String _status = '';
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    try {
      _statusSub = FlutterBackgroundService().on('import_config_status').listen((event) {
        final status = event?['status'] as String?;
        if (mounted && status != null) setState(() => _status = status);
      });
      _resultSub = FlutterBackgroundService().on('import_config_result').listen((event) {
        if (!mounted) return;
        setState(() => _busy = false);
        final success = event?['success'] as bool? ?? false;
        if (!success) return;
        final hostName = event?['host_name'] as String? ?? 'Bilinmeyen Cihaz';
        final configRaw = event?['config'];
        if (configRaw is! Map) return;
        Navigator.pop(context, (hostName, Map<String, dynamic>.from(configRaw)));
      });
    } catch (_) {
      // Arka plan servisi bu platformda/ortamda kullanılamıyor olabilir.
    }
  }

  @override
  void dispose() {
    _statusSub?.cancel();
    _resultSub?.cancel();
    _codeController.dispose();
    super.dispose();
  }

  void _submit() {
    final code = _codeController.text.trim();
    if (code.isEmpty || _busy) return;
    setState(() {
      _busy = true;
      _status = 'Aranıyor...';
    });
    try {
      FlutterBackgroundService().invoke('request_config_export', {'code': code});
    } catch (_) {
      // Arka plan servisi bu platformda/ortamda kullanılamıyor olabilir.
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Kod ile İçe Aktar'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
              'Ayarlarını almak istediğiniz cihazda "Dışa Aktar" ile üretilen kodu '
              'buraya girin.'),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _codeController,
                  decoration: const InputDecoration(labelText: 'Kod'),
                  keyboardType: TextInputType.number,
                  enabled: !_busy,
                ),
              ),
              const SizedBox(width: 8),
              FilledButton(
                onPressed: _busy ? null : _submit,
                child: const Text('İçe Aktar'),
              ),
            ],
          ),
          if (_status.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(_status, style: Theme.of(context).textTheme.bodySmall),
            ),
        ],
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Vazgeç')),
      ],
    );
  }
}
