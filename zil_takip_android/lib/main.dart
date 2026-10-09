import 'dart:async';

import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';

import 'background_service.dart';
import 'config_store.dart';
import 'home_page.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // Arayüz her koşulda hemen açılsın - arka plan servisi kurulumu (bildirim
  // kanalı/foreground service) bazı ortamlarda (ör. emülatörler) yanıt
  // vermeyebilir; bunu burada beklemek tüm uygulamayı sonsuza kadar boş
  // ekranda kilitleyebilirdi.
  runApp(const ZilTakipApp());
  unawaited(_setUpBackgroundService());
}

Future<void> _setUpBackgroundService() async {
  try {
    // Bildirim izni, arka plan servisi başlamadan ÖNCE istenip
    // sonuçlanmalı: servis başlar başlamaz kalıcı bildirimini göstermeye
    // çalışır (bkz. BackgroundService.updateNotificationInfo native
    // tarafta) - izin dialoğu bundan SONRA cevaplanırsa (home_page.dart'ta
    // ayrıca da istenir ama o, HomePage ilk çerçevesi çizildikten sonra,
    // bu fonksiyonla yarış halinde çalışır) bu ilk gösterme denemesi
    // izinsiz başarısız olur ve - kozmetik bir eksiklik değil, servis
    // gerçek "ön plan" korumasını alamadığı için - uygulama arka plana
    // alınır alınmaz (ekran kilidi değil, başka bir uygulamaya geçiş)
    // çalışmayı durdurur. İzin burada, servisten önce ve awaited isteniyor
    // ki ilk gösterme denemesi doğru izin durumuyla yapılsın.
    try {
      await Permission.notification.request();
    } catch (_) {
      // Bu platformda/ortamda izin isteği desteklenmiyor olabilir.
    }
    final config = await loadConfig().timeout(const Duration(seconds: 10));
    await initializeBackgroundService(autoStartOnBoot: config.startOnBoot)
        .timeout(const Duration(seconds: 10));
  } catch (_) {
    // Arka plan servisi bu ortamda kurulamadı; ana arayüz yine de çalışmaya
    // devam eder (zil çalma/ayar ekranları etkilenmez).
  }
}

const Color accent = Color(0xFF2F6F4F);
const Color accentDark = Color(0xFF1F4A34);

class ZilTakipApp extends StatelessWidget {
  const ZilTakipApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Ceselsan Zil Takip',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: accent),
        appBarTheme: const AppBarTheme(
          backgroundColor: accentDark,
          foregroundColor: Colors.white,
        ),
        useMaterial3: true,
      ),
      home: const HomePage(),
    );
  }
}
