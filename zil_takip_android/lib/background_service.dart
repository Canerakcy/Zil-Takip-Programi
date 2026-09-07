// Arka planda çalışan zamanlayıcı - Windows sürümündeki scheduler.py'nin
// karşılığı. Android'de bu, kalıcı bir "foreground service" (ön plan
// servisi) olarak, ekran kapalıyken/uygulama arka plandayken de canlı
// kalacak şekilde ayrı bir Dart isolate'inde çalışır.
import 'dart:async';
import 'dart:ui';

import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import 'audio_player_service.dart';
import 'config_store.dart';
import 'models.dart';
import 'prayer_service.dart';
import 'remote_control.dart';
import 'ring_history.dart';

const String notificationChannelId = 'zil_takip_foreground';
const String notificationChannelName = 'Ceselsan Zil Takip - Arka Plan Servisi';
const int foregroundNotificationId = 888;

/// Her kontrol arasındaki süre. Windows sürümü 5 saniye kullanıyor; telefonda
/// pil tüketimini azaltmak için biraz daha seyrek kontrol ediyoruz - yine de
/// bir dakika içinde birkaç kez kontrol edildiği için hiçbir zil kaçmaz.
const Duration checkInterval = Duration(seconds: 20);

/// Android'de (özellikle pil kısıtlamaları/emülatörler yüzünden) zamanlayıcı
/// bazen bir dakikadan fazla gecikebilir - tam dakika eşleşmesi (==) o anı
/// tamamen kaçırıp zili hiç çalmayabilir. Bunun yerine, planlanan saat
/// geçtikten sonra bu tolerans penceresi içindeyse ve o gün için henüz
/// çalınmadıysa yine de çalınır ("yakalama" mantığı).
const Duration dueGraceWindow = Duration(minutes: 3);

/// [scheduledHhmm] "HH:MM" vaktinin, [now] itibarıyla çalınması gerekip
/// gerekmediğini söyler: vakit geçmiş olmalı ama [dueGraceWindow]'dan daha
/// eski olmamalı (aksi halde uygulama çok sonra açıldığında geçmişteki tüm
/// zilleri art arda çalar).
bool _isDue(String scheduledHhmm, DateTime now) {
  final parts = scheduledHhmm.split(':');
  final hour = int.tryParse(parts[0]);
  final minute = parts.length > 1 ? int.tryParse(parts[1]) : null;
  if (hour == null || minute == null) return false;
  final scheduled = DateTime(now.year, now.month, now.day, hour, minute);
  final diff = now.difference(scheduled);
  return diff >= Duration.zero && diff <= dueGraceWindow;
}

/// [autoStartOnBoot], kullanıcının Genel sekmesindeki "Telefon Açılınca
/// Otomatik Başlat" tercihini (AppConfig.startOnBoot) yansıtır. Bu değer
/// her configure() çağrısında native tarafta kalıcı olarak saklanır; bu
/// yüzden ayar her değiştiğinde bu fonksiyon tekrar çağrılmalıdır.
Future<void> initializeBackgroundService({bool autoStartOnBoot = false}) async {
  final service = FlutterBackgroundService();

  const androidChannel = AndroidNotificationChannel(
    notificationChannelId,
    notificationChannelName,
    description: 'Zil zamanı geldiğinde arka planda çalışmaya devam eder.',
    importance: Importance.low,
  );
  const pairingChannel = AndroidNotificationChannel(
    pairingNotificationChannelId,
    pairingNotificationChannelName,
    description: 'Başka bir cihaz eşleştirme kodu ile bağlanmak istediğinde bildirim gösterir.',
    importance: Importance.high,
  );
  final androidNotifications = FlutterLocalNotificationsPlugin()
      .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin>();
  await androidNotifications?.createNotificationChannel(androidChannel);
  await androidNotifications?.createNotificationChannel(pairingChannel);

  await service.configure(
    androidConfiguration: AndroidConfiguration(
      onStart: onServiceStart,
      autoStart: true,
      isForegroundMode: true,
      notificationChannelId: notificationChannelId,
      initialNotificationTitle: 'Ceselsan Zil Takip',
      initialNotificationContent: 'Arka planda çalışıyor',
      foregroundServiceNotificationId: foregroundNotificationId,
      autoStartOnBoot: autoStartOnBoot,
      // Android 14+ (API 34) foreground servisler için bir tür belirtilmesini
      // zorunlu kılıyor; zil sesi çaldığımız için "mediaPlayback" en uygunu.
      foregroundServiceTypes: const [AndroidForegroundType.mediaPlayback],
    ),
    iosConfiguration: IosConfiguration(),
  );
}

@pragma('vm:entry-point')
void onServiceStart(ServiceInstance service) async {
  DartPluginRegistrant.ensureInitialized();

  final audioPlayer = AudioPlayerService();
  final firedToday = <String>{};
  DateTime? firedDate;
  Map<String, String>? timingsCache;
  DateTime? timingsCacheDate;
  bool holidayNoticeShown = false;

  void log(String message) {
    service.invoke('log', {'message': message, 'time': DateTime.now().toIso8601String()});
  }

  if (service is AndroidServiceInstance) {
    service.on('stopService').listen((event) {
      service.stopSelf();
    });
  }

  await _setUpRemoteControl(service, audioPlayer, log);

  Timer.periodic(checkInterval, (timer) async {
    try {
      final config = await loadConfig();
      final now = DateTime.now();
      final today = DateTime(now.year, now.month, now.day);

      if (firedDate != today) {
        firedDate = today;
        firedToday.clear();
        holidayNoticeShown = false;
      }

      final todayStr =
          '${today.year.toString().padLeft(4, '0')}-${today.month.toString().padLeft(2, '0')}-${today.day.toString().padLeft(2, '0')}';
      final holiday = config.holidays.where((h) => h.date == todayStr).firstOrNull;
      if (holiday != null) {
        if (!holidayNoticeShown) {
          holidayNoticeShown = true;
          log(holiday.ring
              ? 'Bugün tatil (${holiday.label}) - normal program çalmayacak, '
                  '${holiday.ringTime} saatinde özel zil çalacak.'
              : 'Bugün tatil (${holiday.label}) - ziller çalmayacak.');
        }
        final ringTime = holiday.ringTime;
        if (holiday.ring && ringTime != null && _isDue(ringTime, now)) {
          final fireKey = 'holiday:$todayStr';
          if (!firedToday.contains(fireKey)) {
            firedToday.add(fireKey);
            final holidayLabel =
                holiday.label.isNotEmpty ? holiday.label : 'Özel tatil zili';
            log('Zil çalıyor: $holidayLabel');
            final played = await audioPlayer.playFile(
                holiday.ringSound, config.defaultSound, config.volume);
            await recordRing(holidayLabel, 'holiday',
                success: played, error: played ? null : 'Çalınacak ses yok');
          }
        }
        return;
      }

      // Dart'ta DateTime.weekday: Pazartesi=1 ... Pazar=7. Python sürümüyle
      // (Pazartesi=0 ... Pazar=6) tutarlı olması için 1 çıkarılır.
      final weekday = now.weekday - 1;

      for (final entry in config.entries) {
        if (!entry.enabled) continue;
        if (!entry.days.contains(weekday)) continue;
        if (!_isDue(entry.time, now)) continue;
        final fireKey = 'entry:${entry.id}:$todayStr';
        if (firedToday.contains(fireKey)) continue;
        firedToday.add(fireKey);
        log('Zil çalıyor: ${entry.label}');
        final played = await audioPlayer.playFile(entry.sound, config.defaultSound, config.volume);
        await recordRing(entry.label, 'entry',
            success: played, error: played ? null : 'Çalınacak ses yok');
      }

      final pt = config.prayerTimes;
      if (pt.enabled && pt.city.trim().isNotEmpty) {
        if (timingsCacheDate != today) {
          timingsCache = null;
          timingsCacheDate = today;
        }
        timingsCache ??= await _fetchTimingsWithLog(pt.city, pt.country, today, log);

        final timings = timingsCache;
        if (timings != null) {
          for (final vakit in vakitKeys) {
            final setting = pt.daily[vakit];
            if (setting == null || !setting.enabled) continue;
            final baseTime = timings[vakit];
            if (baseTime == null || !_isDue(baseTime, now)) continue;
            final fireKey = 'daily:$vakit:$todayStr';
            if (firedToday.contains(fireKey)) continue;
            firedToday.add(fireKey);
            final vakitLabel = vakitLabels[vakit] ?? vakit;
            log('Zil çalıyor: $vakitLabel');
            final played = await audioPlayer.playFile(
                setting.sound, config.defaultSound, config.volume);
            await recordRing(vakitLabel, 'prayer',
                success: played, error: played ? null : 'Çalınacak ses yok');
          }

          // weekday: Pazartesi=0 ... Cuma=4 (yukarıdaki dönüşümle).
          if (weekday == 4) {
            final ogle = timings['ogle'];
            if (ogle != null) {
              for (final offset in pt.fridayOffsets) {
                if (!offset.enabled) continue;
                final signedMinutes =
                    offset.direction == 'after' ? offset.minutes : -offset.minutes;
                final triggerTime = applyOffsetMinutes(ogle, signedMinutes);
                if (!_isDue(triggerTime, now)) continue;
                final fireKey = 'friday:${offset.id}:$todayStr';
                if (firedToday.contains(fireKey)) continue;
                firedToday.add(fireKey);
                final directionText = offset.direction == 'before' ? 'kala' : 'sonra';
                final label = offset.label.isNotEmpty
                    ? offset.label
                    : 'Cuma Namazı - ${offset.minutes} dk $directionText';
                log('Zil çalıyor: $label');
                final played = await audioPlayer.playFile(
                    offset.sound, config.defaultSound, config.volume);
                await recordRing(label, 'friday',
                    success: played, error: played ? null : 'Çalınacak ses yok');
              }
            }
          }
        }
      }
    } catch (exc) {
      log('Zamanlayıcı hatası: $exc');
    }
  });
}

const String pairingNotificationChannelId = 'zil_takip_pairing';
const String pairingNotificationChannelName = 'Ceselsan Zil Takip - Eşleştirme İstekleri';
const int pairingNotificationId = 889;

/// requestId -> onay/red kararını bildiren fonksiyon. Karar UI'dan
/// 'pairing_decision' olayıyla geldiğinde çağrılır.
final Map<String, void Function(bool)> _pendingPairingDecisions = {};

/// Arka plan servisi (bu izole/isolate) her zaman canlı olduğu için gelen
/// eşleştirme istekleri ve uzaktan komutlar burada, UI (ana isolate) ile
/// [FlutterBackgroundService]'in mevcut olay kanalı (invoke/on - zaten
/// 'log' için kullanılıyordu) üzerinden köprülenerek işlenir.
Future<void> _setUpRemoteControl(
    ServiceInstance service, AudioPlayerService audioPlayer, void Function(String) log) async {
  late final RemoteControlService remoteControl;
  remoteControl = RemoteControlService(
    getConfig: () async => (await loadConfig()).toJson(),
    applyRemoteConfig: (newCfgJson) async {
      await saveConfig(AppConfig.fromJson(newCfgJson));
      // Uygulama açıksa (UI ana isolate'te çalışıyorsa) ekranındaki ayarlar
      // artık diskteki güncel değerle eşleşmiyor - yeniden okunmazsa hem
      // kullanıcı değişikliği canlı görmez hem de bir sonraki yerel
      // düzenlemede eski (bayat) ayar diske geri yazılıp uzaktan gelen
      // değişikliği sessizce siler. Bu yüzden UI'ye "yeniden yükle" sinyali
      // gönderiyoruz (Windows'ta App._apply_remote_config zaten sekmeleri
      // anında yeniden kuruyor - burada aynı canlı yansımayı sağlıyoruz).
      service.invoke('remote_config_updated');
    },
    ringNow: (sound) async {
      final config = await loadConfig();
      await audioPlayer.playFile(sound, config.defaultSound, config.volume);
    },
    stopRinging: audioPlayer.stop,
    onPairingRequest: (name, decide) =>
        _handleIncomingPairingRequest(service, name, decide),
    onLog: log,
    deviceName: 'Android Telefon',
    onDevicesChanged: () {
      savePairedDevicesRaw(remoteControl.pairedDevices.map((p) => p.toJson()).toList());
    },
    initialPairedDevices: (await loadPairedDevicesRaw())
        .map((e) => PairedDevice.fromJson(e))
        .toList(),
  );

  try {
    await remoteControl.start();
  } catch (exc) {
    log('Uzaktan erişim başlatılamadı: $exc');
  }

  service.on('generate_pairing_code').listen((event) {
    final code = remoteControl.generateCode();
    service.invoke('pairing_code', {'code': code});
  });

  service.on('cancel_pairing_code').listen((event) {
    remoteControl.cancelCode();
  });

  service.on('connect_with_code').listen((event) async {
    final code = event?['code'] as String?;
    if (code == null || code.isEmpty) return;
    final peer = await remoteControl.pairWithCode(code, (status) {
      service.invoke('pairing_status', {'status': status});
    });
    service.invoke('pairing_result',
        {'success': peer != null, 'name': peer?.name, 'peer_id': peer?.peerId});
  });

  service.on('get_paired_devices').listen((event) {
    service.invoke('paired_devices_updated',
        {'devices': remoteControl.pairedDevices.map((p) => p.toJson()).toList()});
  });

  service.on('remove_paired_device').listen((event) {
    final peerId = event?['peer_id'] as String?;
    if (peerId != null) remoteControl.removePairedDevice(peerId);
    service.invoke('paired_devices_updated',
        {'devices': remoteControl.pairedDevices.map((p) => p.toJson()).toList()});
  });

  service.on('remote_command').listen((event) async {
    final requestId = event?['request_id'] as String?;
    final peerId = event?['peer_id'] as String?;
    final rawCmd = event?['cmd'];
    final peer = remoteControl.pairedDevices
        .where((p) => p.peerId == peerId)
        .firstOrNull;
    if (peer == null || rawCmd is! Map) {
      service.invoke('remote_command_result',
          {'request_id': requestId, 'error': 'Cihaz bulunamadı.'});
      return;
    }
    try {
      final result =
          await remoteControl.sendCommand(peer, Map<String, dynamic>.from(rawCmd));
      service.invoke('remote_command_result', {'request_id': requestId, 'result': result});
    } catch (exc) {
      service.invoke(
          'remote_command_result', {'request_id': requestId, 'error': exc.toString()});
    }
  });

  service.on('pairing_decision').listen((event) {
    final requestId = event?['request_id'] as String?;
    final approved = event?['approved'] as bool? ?? false;
    final pending = _pendingPairingDecisions.remove(requestId);
    pending?.call(approved);
  });
}

void _handleIncomingPairingRequest(
    ServiceInstance service, String name, void Function(bool) decide) {
  final requestId = uuid.v4();
  _pendingPairingDecisions[requestId] = decide;

  FlutterLocalNotificationsPlugin().show(
    pairingNotificationId,
    'Eşleştirme İsteği',
    "'$name' bu cihaza bağlanmak istiyor - onaylamak için uygulamayı açın.",
    const NotificationDetails(
      android: AndroidNotificationDetails(
        pairingNotificationChannelId,
        pairingNotificationChannelName,
        importance: Importance.high,
        priority: Priority.high,
      ),
    ),
  );

  void emit() => service.invoke('pairing_request', {'request_id': requestId, 'name': name});
  emit();

  var attempts = 0;
  Timer.periodic(const Duration(seconds: 4), (timer) {
    attempts++;
    if (!_pendingPairingDecisions.containsKey(requestId)) {
      timer.cancel();
      return;
    }
    if (attempts > 22) {
      // ~90 saniye boyunca kimse yanıtlamadı - güvenli taraf: reddet.
      timer.cancel();
      _pendingPairingDecisions.remove(requestId);
      decide(false);
      return;
    }
    emit();
  });
}

Future<Map<String, String>?> _fetchTimingsWithLog(String city, String country,
    DateTime today, void Function(String) log) async {
  final (timings, fromNetwork) = await getCachedOrFetchDay(city, country, today);
  if (timings != null) {
    final source = fromNetwork ? 'internetten' : 'önbellekten';
    log('$city için namaz vakitleri $source alındı.');
  } else {
    log('$city için namaz vakitleri alınamadı (internet bağlantısını kontrol edin).');
  }
  return timings;
}

extension _FirstOrNullExtension<T> on Iterable<T> {
  T? get firstOrNull => isEmpty ? null : first;
}
