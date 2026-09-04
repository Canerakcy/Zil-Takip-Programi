// Veri modelleri - Windows sürümündeki config_store.py ile aynı JSON şemasını
// kullanır, böylece iki sürüm arasında ayarlar taşınabilir/tutarlıdır.
import 'package:uuid/uuid.dart';

const uuid = Uuid();

const List<String> vakitKeys = [
  'imsak',
  'gunes',
  'ogle',
  'ikindi',
  'aksam',
  'yatsi',
];

const Map<String, String> vakitLabels = {
  'imsak': 'İmsak',
  'gunes': 'Güneş',
  'ogle': 'Öğle',
  'ikindi': 'İkindi',
  'aksam': 'Akşam',
  'yatsi': 'Yatsı',
};

const List<String> dayNames = [
  'Pazartesi',
  'Salı',
  'Çarşamba',
  'Perşembe',
  'Cuma',
  'Cumartesi',
  'Pazar',
];

const List<String> dayShort = [
  'Pzt',
  'Sal',
  'Çar',
  'Per',
  'Cum',
  'Cmt',
  'Paz',
];

class BellEntry {
  String id;
  String label;
  String time; // "HH:MM"
  List<int> days; // 0=Pazartesi..6=Pazar
  String? sound; // null/"default" -> varsayılan ses
  bool enabled;

  BellEntry({
    required this.id,
    required this.label,
    required this.time,
    required this.days,
    this.sound,
    this.enabled = true,
  });

  factory BellEntry.fromJson(Map<String, dynamic> json) => BellEntry(
        id: json['id'] as String,
        label: json['label'] as String? ?? 'Zil',
        time: json['time'] as String? ?? '08:00',
        days: (json['days'] as List<dynamic>? ?? const [])
            .map((e) => e as int)
            .toList(),
        sound: json['sound'] as String?,
        enabled: json['enabled'] as bool? ?? true,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'label': label,
        'time': time,
        'days': days,
        'sound': sound,
        'enabled': enabled,
      };
}

class DailyVakitSetting {
  bool enabled;
  String? sound;

  DailyVakitSetting({this.enabled = false, this.sound});

  factory DailyVakitSetting.fromJson(Map<String, dynamic> json) =>
      DailyVakitSetting(
        enabled: json['enabled'] as bool? ?? false,
        sound: json['sound'] as String?,
      );

  Map<String, dynamic> toJson() => {'enabled': enabled, 'sound': sound};
}

class FridayOffset {
  String id;
  int minutes;
  String direction; // "before" | "after"
  String label;
  String? sound;
  bool enabled;

  FridayOffset({
    required this.id,
    required this.minutes,
    required this.direction,
    required this.label,
    this.sound,
    this.enabled = true,
  });

  factory FridayOffset.fromJson(Map<String, dynamic> json) => FridayOffset(
        id: json['id'] as String,
        minutes: json['minutes'] as int? ?? 15,
        direction: json['direction'] as String? ?? 'before',
        label: json['label'] as String? ?? '',
        sound: json['sound'] as String?,
        enabled: json['enabled'] as bool? ?? true,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'minutes': minutes,
        'direction': direction,
        'label': label,
        'sound': sound,
        'enabled': enabled,
      };

  static FridayOffset createDefault({
    int minutes = 15,
    String direction = 'before',
    String label = '',
    String? sound,
    bool enabled = true,
  }) {
    return FridayOffset(
      id: uuid.v4(),
      minutes: minutes,
      direction: direction,
      label: label,
      sound: sound,
      enabled: enabled,
    );
  }
}

class Holiday {
  String date; // "YYYY-MM-DD"
  String label;

  Holiday({required this.date, required this.label});

  factory Holiday.fromJson(Map<String, dynamic> json) => Holiday(
        date: json['date'] as String,
        label: json['label'] as String? ?? '',
      );

  Map<String, dynamic> toJson() => {'date': date, 'label': label};
}

class PrayerTimesConfig {
  bool enabled;
  String city;
  String country;
  Map<String, DailyVakitSetting> daily;
  List<FridayOffset> fridayOffsets;

  PrayerTimesConfig({
    required this.enabled,
    required this.city,
    required this.country,
    required this.daily,
    required this.fridayOffsets,
  });

  factory PrayerTimesConfig.fromJson(Map<String, dynamic> json) {
    final dailyJson = json['daily'] as Map<String, dynamic>? ?? {};
    final daily = <String, DailyVakitSetting>{};
    for (final vakit in vakitKeys) {
      final raw = dailyJson[vakit] as Map<String, dynamic>?;
      daily[vakit] =
          raw != null ? DailyVakitSetting.fromJson(raw) : DailyVakitSetting();
    }
    final offsetsJson = json['friday_offsets'] as List<dynamic>? ?? const [];
    return PrayerTimesConfig(
      enabled: json['enabled'] as bool? ?? true,
      city: json['city'] as String? ?? 'İstanbul',
      country: json['country'] as String? ?? 'Turkey',
      daily: daily,
      fridayOffsets: offsetsJson
          .map((e) => FridayOffset.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }

  Map<String, dynamic> toJson() => {
        'enabled': enabled,
        'city': city,
        'country': country,
        'daily': daily.map((key, value) => MapEntry(key, value.toJson())),
        'friday_offsets': fridayOffsets.map((e) => e.toJson()).toList(),
      };

  static PrayerTimesConfig createDefault() {
    return PrayerTimesConfig(
      enabled: true,
      city: 'İstanbul',
      country: 'Turkey',
      daily: {for (final v in vakitKeys) v: DailyVakitSetting()},
      fridayOffsets: [
        FridayOffset.createDefault(
            minutes: 30, direction: 'before', label: 'Cuma Namazı - 30 dk kala'),
        FridayOffset.createDefault(
            minutes: 15, direction: 'before', label: 'Cuma Namazı - 15 dk kala'),
        FridayOffset.createDefault(
            minutes: 30,
            direction: 'after',
            label: 'Cuma Namazı Sonrası - Mesaiye Dönüş (30 dk sonra)',
            enabled: false),
      ],
    );
  }
}

class AppConfig {
  String? defaultSound;
  double volume;
  List<BellEntry> entries;
  PrayerTimesConfig prayerTimes;
  bool startOnBoot;
  List<Holiday> holidays;

  AppConfig({
    required this.defaultSound,
    required this.volume,
    required this.entries,
    required this.prayerTimes,
    required this.startOnBoot,
    required this.holidays,
  });

  factory AppConfig.fromJson(Map<String, dynamic> json) {
    final entriesJson = json['entries'] as List<dynamic>? ?? const [];
    final holidaysJson = json['holidays'] as List<dynamic>? ?? const [];
    return AppConfig(
      defaultSound: json['default_sound'] as String?,
      volume: (json['volume'] as num?)?.toDouble() ?? 1.0,
      entries: entriesJson
          .map((e) => BellEntry.fromJson(e as Map<String, dynamic>))
          .toList(),
      prayerTimes: json['prayer_times'] != null
          ? PrayerTimesConfig.fromJson(
              json['prayer_times'] as Map<String, dynamic>)
          : PrayerTimesConfig.createDefault(),
      startOnBoot: json['start_on_boot'] as bool? ?? false,
      holidays: holidaysJson
          .map((e) => Holiday.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }

  Map<String, dynamic> toJson() => {
        'default_sound': defaultSound,
        'volume': volume,
        'entries': entries.map((e) => e.toJson()).toList(),
        'prayer_times': prayerTimes.toJson(),
        'start_on_boot': startOnBoot,
        'holidays': holidays.map((e) => e.toJson()).toList(),
      };

  static AppConfig createDefault() {
    return AppConfig(
      defaultSound: null,
      volume: 1.0,
      entries: [
        BellEntry(
          id: uuid.v4(),
          label: '1. Ders Başlangıcı',
          time: '08:30',
          days: const [0, 1, 2, 3, 4],
          sound: null,
          enabled: true,
        ),
      ],
      prayerTimes: PrayerTimesConfig.createDefault(),
      startOnBoot: false,
      holidays: [],
    );
  }
}
