// Basit widget smoke testi - uygulamanın hatasız açılıp yükleme ekranını
// gösterdiğini doğrular.
//
// Not: Sekmelerin (Zil Programı/Namaz Vakitleri/Genel) tam olarak
// yüklenmiş halini test etmek, gerçek dart:io dosya G/Ç'si ve
// path_provider/audioplayers gibi platform eklentilerini gerektiriyor;
// bunlar `flutter test`'in sahte-zaman (FakeAsync) test ortamında güvenilir
// şekilde tamamlanmıyor (yalnızca gerçek bir Android cihaz/emülatörde
// çalışırlar). Bu yüzden burada sadece uygulamanın çökmeden açıldığı
// doğrulanır; tam entegrasyon testi gerçek cihazda yapılmalıdır.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:zil_takip_android/main.dart';

void main() {
  testWidgets('Uygulama çökmeden açılır', (WidgetTester tester) async {
    await tester.pumpWidget(const ZilTakipApp());
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    // Gerçek dart:io tabanlı config yüklemesi bu sahte-zaman test ortamında
    // tamamlanmadığından (bkz. yorumlar yukarıda), _load()'daki 10 saniyelik
    // zaman aşımının temiz bir şekilde ateşlenip iptal edilmesi için saatin
    // ileri alınması gerekir - aksi halde test "pending timer" hatasıyla
    // başarısız olur.
    await tester.pump(const Duration(seconds: 11));
  });
}
