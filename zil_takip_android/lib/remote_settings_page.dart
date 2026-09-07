// Eşleşmiş bir uzak cihazın TÜM ayarlarını görüntüleme/değiştirme ekranı.
// Mevcut Zil Programı/Namaz Vakitleri/Genel sekmeleri zaten (config,
// onChanged) çiftine göre çalıştığından - yerel diske mi yoksa uzak cihaza
// mı kaydedildiğini bilmezler - burada aynı widget'lar, onChanged'i uzak
// cihaza "set_config" komutu gönderecek şekilde yeniden kullanılır.
import 'package:flutter/material.dart';

import 'entries_tab.dart';
import 'general_tab.dart';
import 'models.dart';
import 'prayer_tab.dart';
import 'remote_bridge.dart';
import 'remote_control.dart';

class RemoteSettingsPage extends StatefulWidget {
  final PairedDevice peer;

  const RemoteSettingsPage({super.key, required this.peer});

  @override
  State<RemoteSettingsPage> createState() => _RemoteSettingsPageState();
}

class _RemoteSettingsPageState extends State<RemoteSettingsPage> {
  final RemoteCommandBridge _bridge = RemoteCommandBridge();
  AppConfig? _config;
  String? _error;
  bool _saving = false;
  int _selectedIndex = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _bridge.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final result = await _bridge.send(widget.peer.peerId, {'cmd': 'get_config'});
      if (!mounted) return;
      if (result['ok'] != true) {
        setState(() => _error = result['error']?.toString() ?? 'Ayarlar alınamadı.');
        return;
      }
      final data = result['data'];
      setState(() => _config = AppConfig.fromJson(Map<String, dynamic>.from(data as Map)));
    } catch (exc) {
      if (!mounted) return;
      setState(() => _error = "'${widget.peer.name}' cihazına bağlanılamadı: $exc");
    }
  }

  Future<void> _push() async {
    final config = _config;
    if (config == null) return;
    setState(() => _saving = true);
    try {
      final result = await _bridge
          .send(widget.peer.peerId, {'cmd': 'set_config', 'config': config.toJson()});
      if (!mounted) return;
      if (result['ok'] != true) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text('Gönderilemedi: ${result['error']}')));
      }
    } catch (exc) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Gönderilemedi: $exc')));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  void _onChanged() {
    setState(() {});
    _push();
  }

  Future<void> _onTest(String? sound) async {
    try {
      final result = await _bridge
          .send(widget.peer.peerId, {'cmd': 'ring_now', 'sound': sound});
      if (!mounted) return;
      if (result['ok'] != true) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text('Uzak cihazda çalınamadı: ${result['error']}')));
      }
    } catch (exc) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Uzak cihazda çalınamadı: $exc')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final config = _config;
    return Scaffold(
      appBar: AppBar(
        title: Text('${widget.peer.name} - Uzak Ayarlar'),
        actions: [
          if (_saving)
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 16),
              child: Center(
                child: SizedBox(
                    width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
              ),
            ),
        ],
      ),
      body: _error != null
          ? Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(_error!, textAlign: TextAlign.center),
                    const SizedBox(height: 16),
                    FilledButton(
                        onPressed: () {
                          setState(() => _error = null);
                          _load();
                        },
                        child: const Text('Tekrar Dene')),
                  ],
                ),
              ),
            )
          : config == null
              ? const Center(child: CircularProgressIndicator())
              : IndexedStack(
                  index: _selectedIndex,
                  children: [
                    EntriesTab(config: config, onChanged: _onChanged, onTest: _onTest),
                    PrayerTab(config: config, onChanged: _onChanged, onTest: _onTest),
                    GeneralTab(
                        config: config,
                        onChanged: _onChanged,
                        logLines: const [],
                        isRemote: true),
                  ],
                ),
      bottomNavigationBar: config == null
          ? null
          : NavigationBar(
              selectedIndex: _selectedIndex,
              onDestinationSelected: (index) => setState(() => _selectedIndex = index),
              destinations: const [
                NavigationDestination(
                    icon: Icon(Icons.notifications_active), label: 'Zil Programı'),
                NavigationDestination(icon: Icon(Icons.mosque), label: 'Namaz Vakitleri'),
                NavigationDestination(icon: Icon(Icons.settings), label: 'Genel'),
              ],
            ),
    );
  }
}
