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
  await FlutterLocalNotificationsPlugin()
      .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin>()
      ?.createNotificationChannel(androidChannel);

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
          log('Bugün tatil (${holiday.label}) - ziller çalmayacak.');
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
        await audioPlayer.playFile(entry.sound, config.defaultSound, config.volume);
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
            log('Zil çalıyor: ${vakitLabels[vakit]}');
            await audioPlayer.playFile(
                setting.sound, config.defaultSound, config.volume);
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
                await audioPlayer.playFile(
                    offset.sound, config.defaultSound, config.volume);
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
