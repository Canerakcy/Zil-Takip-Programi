import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:permission_handler/permission_handler.dart';

import 'audio_player_service.dart';
import 'config_store.dart';
import 'general_tab.dart';
import 'models.dart';
import 'prayer_tab.dart';
import 'entries_tab.dart';

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
  AudioPlayerService? _testPlayerInstance;
  AudioPlayerService get _testPlayer =>
      _testPlayerInstance ??= AudioPlayerService();

  @override
  void initState() {
    super.initState();
    _load();
    _requestNotificationPermission();
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
  }

  @override
  void dispose() {
    _logSub?.cancel();
    _testPlayerInstance?.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final config = await loadConfig();
    setState(() => _config = config);
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

  Future<void> _persist() async {
    final config = _config;
    if (config == null) return;
    await saveConfig(config);
    setState(() {});
  }

  Future<void> _testSound(String? sound) async {
    final config = _config;
    if (config == null) return;
    await _testPlayer.playFile(sound, config.defaultSound, config.volume);
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
      GeneralTab(config: config, onChanged: _persist, logLines: _logLines),
    ];

    return Scaffold(
      appBar: AppBar(
        title: const Text('🔔 Ceselsan Zil Takip'),
      ),
      body: IndexedStack(index: _selectedIndex, children: tabs),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedIndex,
        onDestinationSelected: (index) => setState(() => _selectedIndex = index),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.notifications_active), label: 'Zil Programı'),
          NavigationDestination(icon: Icon(Icons.mosque), label: 'Namaz Vakitleri'),
          NavigationDestination(icon: Icon(Icons.settings), label: 'Genel'),
        ],
      ),
    );
  }
}
