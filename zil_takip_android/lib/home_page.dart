import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:permission_handler/permission_handler.dart';

import 'audio_player_service.dart';
import 'config_store.dart';
import 'dialogs.dart';
import 'general_tab.dart';
import 'models.dart';
import 'prayer_tab.dart';
import 'entries_tab.dart';
import 'remote_tab.dart';
import 'ring_history.dart';
import 'stats_tab.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  AppConfig? _config;
  int _selectedIndex = 0;
  final List<String> _logLines = [];
  StreamSubscription<Map<String, dynamic>?>? _logSub;
  StreamSubscription<Map<String, dynamic>?>? _pairingRequestSub;
  StreamSubscription<Map<String, dynamic>?>? _remoteConfigUpdatedSub;
  AudioPlayerService? _testPlayerInstance;
  AudioPlayerService get _testPlayer => _testPlayerInstance ??=
      AudioPlayerService(onError: _showAudioError);

  void _showAudioError(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  void initState() {
    super.initState();
    _load();
    _requestNotificationPermission();
    _requestBatteryOptimizationExemption();
    try {
      _logSub = FlutterBackgroundService().on('log').listen((event) {
        if (event == null) return;
        final message = event['message'] as String? ?? '';
        setState(() {
          _logLines.insert(0, message);
          if (_logLines.length > 100) _logLines.removeLast();
        });
      });
    } catch (_) {
      // Arka plan servisi bu platformda/ortamda kullanılamıyor olabilir
      // (ör. desteklenmeyen platform); kayıt akışı olmadan da arayüz çalışmaya devam eder.
    }
    try {
      // Bir eşleştirme isteği hangi sekmede olursanız olun görünmeli - bu
      // yüzden dinleyici tüm sekmelerin üstündeki HomePage'de kuruluyor.
      _pairingRequestSub =
          FlutterBackgroundService().on('pairing_request').listen((event) {
        final requestId = event?['request_id'] as String?;
        final name = event?['name'] as String?;
        if (requestId == null || name == null) return;
        _showPairingRequestDialog(requestId, name);
      });
    } catch (_) {
      // Arka plan servisi bu platformda/ortamda kullanılamıyor olabilir.
    }
    try {
      // Bu cihaz başka bir cihaz tarafından uzaktan kontrol edilirken (bkz.
      // background_service.dart applyRemoteConfig) ekran açık olabilir -
      // ayarlar değiştiğinde bunu diskten yeniden okuyup canlı olarak
      // yansıtıyoruz. Bu olmadan hem ekran bayat kalır hem de kullanıcı
      // burada herhangi bir yerel değişiklik yaparsa uzaktan gelen
      // değişiklik sessizce üzerine yazılıp kaybolur.
      _remoteConfigUpdatedSub =
          FlutterBackgroundService().on('remote_config_updated').listen((_) {
        _reloadConfig();
      });
    } catch (_) {
      // Arka plan servisi bu platformda/ortamda kullanılamıyor olabilir.
    }
  }

  final Set<String> _shownPairingRequestIds = {};

  Future<void> _showPairingRequestDialog(String requestId, String name) async {
    // Arka plan servisi, UI hazır olana kadar isteği birkaç saniyede bir
    // tekrar gönderir - burada aynı istek için ikinci bir diyalog açılmasın.
    if (!mounted || _shownPairingRequestIds.contains(requestId)) return;
    _shownPairingRequestIds.add(requestId);
    final approved = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        title: const Text('Eşleştirme İsteği'),
        content: Text(
            "'$name' bu cihaza eşleştirme kodu ile bağlanmak istiyor.\n\n"
            'Onaylıyor musunuz? Onaylarsanız bu cihaz zili uzaktan '
            'çaldırabilir, durdurabilir ve tüm ayarları görüntüleyip '
            'değiştirebilir.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false), child: const Text('Hayır')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true), child: const Text('Evet')),
        ],
      ),
    );
    _shownPairingRequestIds.remove(requestId);
    FlutterBackgroundService()
        .invoke('pairing_decision', {'request_id': requestId, 'approved': approved ?? false});
  }

  @override
  void dispose() {
    _logSub?.cancel();
    _pairingRequestSub?.cancel();
    _remoteConfigUpdatedSub?.cancel();
    _testPlayerInstance?.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    AppConfig config;
    try {
      config = await loadConfig().timeout(const Duration(seconds: 10));
    } catch (_) {
      // Ayarlar diskten okunamadı (ör. bir platform eklentisi bu ortamda
      // yanıt vermiyor) - kullanıcı sonsuza kadar yükleniyor ekranında
      // kalmasın diye varsayılan ayarlarla devam edilir.
      config = AppConfig.createDefault();
    }
    if (!mounted) return;
    setState(() => _config = config);
    if (config.defaultSound == null) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _promptDefaultSound());
    }
  }

  Future<void> _reloadConfig() async {
    AppConfig config;
    try {
      config = await loadConfig().timeout(const Duration(seconds: 10));
    } catch (_) {
      return;
    }
    if (!mounted) return;
    setState(() => _config = config);
  }

  Future<void> _promptDefaultSound() async {
    // Windows sürümünde olduğu gibi, ilk açılışta kullanıcıdan bir zil sesi
    // seçmesi istenir - aksi halde "Test Et" butonlarına basınca hiçbir şey
    // duyulmaz (çalınacak ses yok) ve bu bir hata gibi görünür.
    if (!mounted) return;
    final config = _config;
    if (config == null || config.defaultSound != null) return;
    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        title: const Text('Varsayılan Zil Sesi Seçin'),
        content: const Text(
            'Zillerin çalabilmesi için önce bir ses dosyası (.mp3/.wav vb.) '
            'seçmeniz gerekiyor. Bu ses, kendi sesi olmayan tüm kayıtlar için '
            'kullanılır.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Daha Sonra'),
          ),
          FilledButton(
            onPressed: () async {
              Navigator.pop(ctx);
              final path = await pickSoundFile();
              if (path == null || !mounted) return;
              setState(() => config.defaultSound = path);
              await _persist();
            },
            child: const Text('Ses Seç'),
          ),
        ],
      ),
    );
  }

  Future<void> _requestNotificationPermission() async {
    // Arka plan servisinin kalıcı bildirimi görünür olsun diye
    // (Android 13+'ta çalışma zamanında izin istenmesi gerekir).
    try {
      await Permission.notification.request();
    } catch (_) {
      // Bu platformda/ortamda izin isteği desteklenmiyor olabilir.
    }
  }

  Future<void> _requestBatteryOptimizationExemption() async {
    // Android'in pil optimizasyonu, foreground service + bildirim olsa bile
    // bazı üreticilerde (özellikle Samsung) arka plan servisini bir süre
    // sonra durdurabiliyor. Bu izin, uygulamayı o kısıtlamadan muaf tutar -
    // zil takibinin ekran kapalıyken/uygulama arka plandayken kesintisiz
    // çalışması için gereklidir.
    try {
      final status = await Permission.ignoreBatteryOptimizations.status;
      if (!status.isGranted) {
        await Permission.ignoreBatteryOptimizations.request();
      }
    } catch (_) {
      // Bu platformda/ortamda desteklenmiyor olabilir.
    }
  }

  Future<void> _persist() async {
    final config = _config;
    if (config == null) return;
    await saveConfig(config);
    setState(() {});
  }

  Future<void> _importConfig(AppConfig imported) async {
    setState(() => _config = imported);
    await _persist();
  }

  Future<void> _testSound(String? sound) async {
    final config = _config;
    if (config == null) return;
    final played =
        await _testPlayer.playFile(sound, config.defaultSound, config.volume);
    if (!played && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text(
            'Çalınacak ses yok - önce bu kayıt için bir ses seçin ya da '
            'Genel sekmesinden varsayılan sesi ayarlayın.'),
      ));
    }
  }

  Future<void> _ringFireButton() async {
    final config = _config;
    if (config == null) return;
    final played = await _testPlayer.playFile(
        config.fireButtonSound, config.defaultSound, config.volume);
    await recordRing('Yangın Butonu', 'fire_button',
        success: played, error: played ? null : 'Çalınacak ses yok');
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(played
          ? 'Yangın zili çalıyor!'
          : 'Çalınacak ses yok - Genel sekmesinden yangın butonu sesini '
              'ya da varsayılan sesi ayarlayın.'),
      backgroundColor: played ? Colors.red[700] : null,
    ));
  }

  @override
  Widget build(BuildContext context) {
    final config = _config;
    if (config == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    final tabs = [
      EntriesTab(config: config, onChanged: _persist, onTest: _testSound),
      PrayerTab(config: config, onChanged: _persist, onTest: _testSound),
      GeneralTab(
        config: config,
        onChanged: _persist,
        logLines: _logLines,
        onImportConfig: _importConfig,
      ),
      const StatsTab(),
      const RemoteTab(),
    ];

    return Scaffold(
      appBar: AppBar(
        title: const Text('🔔 Ceselsan Zil Takip'),
      ),
      body: IndexedStack(index: _selectedIndex, children: tabs),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _ringFireButton,
        backgroundColor: Colors.red[700],
        foregroundColor: Colors.white,
        icon: const Icon(Icons.local_fire_department),
        label: const Text('YANGIN'),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedIndex,
        onDestinationSelected: (index) => setState(() => _selectedIndex = index),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.notifications_active), label: 'Zil Programı'),
          NavigationDestination(icon: Icon(Icons.mosque), label: 'Namaz Vakitleri'),
          NavigationDestination(icon: Icon(Icons.settings), label: 'Genel'),
          NavigationDestination(icon: Icon(Icons.bar_chart), label: 'İstatistikler'),
          NavigationDestination(icon: Icon(Icons.wifi_tethering), label: 'Uzaktan Erişim'),
        ],
      ),
    );
  }
}
