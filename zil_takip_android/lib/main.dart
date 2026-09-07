import 'package:flutter/material.dart';

import 'background_service.dart';
import 'config_store.dart';
import 'home_page.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final config = await loadConfig();
  await initializeBackgroundService(autoStartOnBoot: config.startOnBoot);
  runApp(const ZilTakipApp());
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
