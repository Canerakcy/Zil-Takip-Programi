// "Uzaktan Erişim" sekmesi - cihaz eşleştirme (kod oluşturma/kod ile
// bağlanma) ve eşleşmiş cihazlar üzerinde uzaktan müdahale (zil çal/durdur,
// ayarları görüntüle/değiştir). Windows sürümündeki "🔗 Uzaktan Erişim"
// sekmesinin karşılığıdır - aynı yerel ağ (WiFi/LAN) protokolünü konuşur.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_background_service/flutter_background_service.dart';

import 'remote_bridge.dart';
import 'remote_control.dart';
import 'remote_settings_page.dart';

class RemoteTab extends StatefulWidget {
  const RemoteTab({super.key});

  @override
  State<RemoteTab> createState() => _RemoteTabState();
}

class _RemoteTabState extends State<RemoteTab> {
  String? _pairingCode;
  String _connectStatus = '';
  final TextEditingController _codeController = TextEditingController();
  List<PairedDevice> _pairedDevices = [];
  bool _connecting = false;
  late final RemoteCommandBridge _bridge;

  @override
  void initState() {
    super.initState();
    _bridge = RemoteCommandBridge();
    try {
      FlutterBackgroundService().on('pairing_code').listen((event) {
        final code = event?['code'] as String?;
        if (mounted && code != null) setState(() => _pairingCode = code);
      });
      FlutterBackgroundService().on('pairing_status').listen((event) {
        final status = event?['status'] as String?;
        if (mounted && status != null) setState(() => _connectStatus = status);
      });
      FlutterBackgroundService().on('pairing_result').listen((event) {
        if (!mounted) return;
        final success = event?['success'] as bool? ?? false;
        setState(() {
          _connecting = false;
          _connectStatus = success
              ? "'${event?['name']}' ile eşleşti."
              : (_connectStatus.isEmpty ? 'Eşleştirme başarısız.' : _connectStatus);
        });
        if (success) _refreshPairedDevices();
      });
      FlutterBackgroundService().on('paired_devices_updated').listen((event) {
        final raw = event?['devices'];
        if (!mounted || raw is! List) return;
        setState(() {
          _pairedDevices = raw
              .map((e) => PairedDevice.fromJson(Map<String, dynamic>.from(e as Map)))
              .toList();
        });
      });
      _refreshPairedDevices();
    } catch (_) {
      // Arka plan servisi bu platformda/ortamda kullanılamıyor olabilir.
    }
  }

  @override
  void dispose() {
    _codeController.dispose();
    _bridge.dispose();
    super.dispose();
  }

  void _refreshPairedDevices() {
    try {
      FlutterBackgroundService().invoke('get_paired_devices');
    } catch (_) {
      // Arka plan servisi bu platformda/ortamda kullanılamıyor olabilir.
    }
  }

  Future<void> _copyPairingCode() async {
    final code = _pairingCode;
    if (code == null) return;
    await Clipboard.setData(ClipboardData(text: code));
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(const SnackBar(content: Text('Kod kopyalandı.')));
  }

  void _generateCode() {
    try {
      FlutterBackgroundService().invoke('generate_pairing_code');
    } catch (_) {
      // Arka plan servisi bu platformda/ortamda kullanılamıyor olabilir.
    }
  }

  void _connectWithCode() {
    final code = _codeController.text.trim();
    if (code.isEmpty) return;
    setState(() {
      _connecting = true;
      _connectStatus = 'Aranıyor...';
    });
    try {
      FlutterBackgroundService().invoke('connect_with_code', {'code': code});
    } catch (_) {
      // Arka plan servisi bu platformda/ortamda kullanılamıyor olabilir.
    }
  }

  void _removeDevice(PairedDevice peer) {
    showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Eşleştirmeyi Kaldır'),
        content: Text("'${peer.name}' eşleştirmesi kaldırılsın mı?"),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Vazgeç')),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Kaldır')),
        ],
      ),
    ).then((confirmed) {
      if (confirmed != true) return;
      try {
        FlutterBackgroundService().invoke('remove_paired_device', {'peer_id': peer.peerId});
      } catch (_) {
        // Arka plan servisi bu platformda/ortamda kullanılamıyor olabilir.
      }
    });
  }

  Future<void> _ringDevice(PairedDevice peer) async {
    try {
      final result = await _bridge.send(peer.peerId, {'cmd': 'ring_now', 'sound': null});
      if (!mounted) return;
      _showSnack(result['ok'] == true
          ? "'${peer.name}' cihazında zil çaldırıldı."
          : "'${peer.name}' reddetti: ${result['error']}");
    } catch (exc) {
      if (mounted) _showSnack("'${peer.name}' cihazına ulaşılamadı: $exc");
    }
  }

  Future<void> _stopDevice(PairedDevice peer) async {
    try {
      final result = await _bridge.send(peer.peerId, {'cmd': 'stop'});
      if (!mounted) return;
      _showSnack(result['ok'] == true
          ? "'${peer.name}' cihazında durduruldu."
          : "'${peer.name}' reddetti: ${result['error']}");
    } catch (exc) {
      if (mounted) _showSnack("'${peer.name}' cihazına ulaşılamadı: $exc");
    }
  }

  void _openSettings(PairedDevice peer) {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => RemoteSettingsPage(peer: peer)),
    );
  }

  void _showSnack(String message) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Bu Cihazı Eşleştir', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 4),
        Text(
          'Bir eşleştirme kodu oluşturun ve karşı cihaza girin. Onayladığınızda '
          'karşı cihaz zili uzaktan çaldırabilir/durdurabilir ve tüm ayarları '
          'görüntüleyip değiştirebilir. Yalnızca aynı yerel ağda (WiFi) çalışır.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: 12),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                FilledButton.icon(
                  onPressed: _generateCode,
                  icon: const Icon(Icons.vpn_key),
                  label: const Text('Kod Oluştur'),
                ),
                // Kod 5-20 hane olabildiğinden, butonla aynı satıra
                // sığdırmaya çalışmak (eski tasarım) uzun kodların
                // kesilmesine/görünmemesine yol açıyordu - kendi geniş
                // satırında, kaydırabilen ve uzun basılıp kopyalanabilen
                // seçilebilir bir metin olarak gösteriliyor.
                if (_pairingCode != null) ...[
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      Expanded(
                        child: SelectableText(
                          _pairingCode!,
                          style: const TextStyle(
                              fontSize: 24, fontWeight: FontWeight.bold, letterSpacing: 1),
                        ),
                      ),
                      IconButton(
                        icon: const Icon(Icons.copy),
                        tooltip: 'Kopyala',
                        onPressed: _copyPairingCode,
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '5 dakika içinde girilmezse ya da bir kez kullanılınca bu kod geçersiz '
                    'olur - yeni bir kod için tekrar oluşturun.',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ],
            ),
          ),
        ),
        const SizedBox(height: 24),
        Text('Başka Bir Cihaza Bağlan', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _codeController,
                        decoration: const InputDecoration(labelText: 'Kod'),
                        keyboardType: TextInputType.number,
                      ),
                    ),
                    const SizedBox(width: 12),
                    FilledButton(
                      onPressed: _connecting ? null : _connectWithCode,
                      child: const Text('Bağlan'),
                    ),
                  ],
                ),
                if (_connectStatus.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(_connectStatus,
                        style: Theme.of(context).textTheme.bodySmall),
                  ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 24),
        Text('Eşleşmiş Cihazlar', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        if (_pairedDevices.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 8),
            child: Text('Henüz eşleşmiş cihaz yok.'),
          ),
        for (final peer in _pairedDevices)
          Card(
            child: ListTile(
              title: Text(peer.name),
              subtitle: const Text('Eşleşmiş cihaz'),
              onTap: () => _openSettings(peer),
              trailing: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  IconButton(
                    icon: const Icon(Icons.notifications_active),
                    tooltip: 'Zili Çal',
                    onPressed: () => _ringDevice(peer),
                  ),
                  IconButton(
                    icon: const Icon(Icons.stop_circle_outlined),
                    tooltip: 'Durdur',
                    onPressed: () => _stopDevice(peer),
                  ),
                  IconButton(
                    icon: const Icon(Icons.settings_outlined),
                    tooltip: 'Ayarları Görüntüle/Değiştir',
                    onPressed: () => _openSettings(peer),
                  ),
                  IconButton(
                    icon: const Icon(Icons.delete_outline),
                    tooltip: 'Kaldır',
                    onPressed: () => _removeDevice(peer),
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }
}
