# 🔔 Ceselsan Zil Takip Programı

Okul/kurum zil saatlerini otomatik olarak çalan, Windows için masaüstü
uygulaması. Kaynak kodu `zil_takip/` klasöründedir, Python + Tkinter ile
yazılmıştır.

## 📥 İndir

Kuruluma gerek yok, GitHub hesabı da gerekmiyor — aşağıdaki linke
tıklamanız yeterli:

**👉 [CeselsanZilTakip.exe indir](https://github.com/Canerakcy/Zil-Takip-Programi/releases/latest/download/CeselsanZilTakip.exe)**

### ⚠️ "Windows bu uygulamayı tanımıyor" uyarısı çıkarsa

Bu, **virüs ya da zararlı yazılım olduğu anlamına gelmez.** Windows
SmartScreen, ücretli bir "kod imzalama sertifikası" ile imzalanmamış her
küçük/bağımsız uygulama için bu uyarıyı gösterir - ücretsiz/açık kaynak
projelerde çok yaygındır. Devam etmek için:

1. Uyarı penceresinde **"Daha fazla bilgi"** (More info) yazısına tıklayın.
2. Açılan **"Yine de çalıştır"** (Run anyway) butonuna basın.

(Bu proje açık kaynaktır, kaynak kodun tamamı bu depoda - isterseniz
`zil_takip/` klasöründeki kodu inceleyip kendiniz de derleyebilirsiniz;
bkz. aşağıdaki "Kendi bilgisayarınızda elle derlemek" bölümü.)

## Ekran Görüntüleri

| Zil Programı | Cuma Namazı |
|---|---|
| ![Zil Programı](docs/screenshots/01_zil_programi.png) | ![Cuma Namazı](docs/screenshots/02_cuma_namazi.png) |

| Ses Ayarları | Yeni Zil Ekleme |
|---|---|
| ![Ses Ayarları](docs/screenshots/03_ses_ayarlari.png) | ![Zil Ekle](docs/screenshots/04_zil_ekle_penceresi.png) |

**Namazdan önce/sonra zil ekleme** (her kurumun mola/mesai süresi
farklı olduğu için tamamen size bağlı):

![Cuma Zil Zamanı](docs/screenshots/05_cuma_zil_zamani_penceresi.png)

**Genel Ayarlar** (sistem tepsisi, Windows'ta otomatik başlatma, tatil günleri):

![Genel Ayarlar](docs/screenshots/06_genel_ayarlar.png)

## Özellikler

- **Haftalık zil programı**: İstediğiniz saatlerde, istediğiniz günlerde
  otomatik zil çalar (ders başlangıç/bitiş saatleri, teneffüs vb.).
- **Hoparlör seçimi**: Sesin hangi ses çıkış cihazından (hoparlör,
  kulaklık, harici ses kartı vb.) çalınacağını Ses Ayarları sekmesinden
  seçebilirsiniz.
- **Kendi ses dosyanızı seçersiniz**: Program herhangi bir zil sesi
  üretmez/içermez. İlk açılışta ve her zil kaydında istediğiniz .wav/.mp3/
  .ogg/.flac dosyasını seçmeniz istenir.
- **Namaz vakitleri (ayırt edici özellik)**: Seçtiğiniz il/ilçe için
  günlük namaz vakitlerini (İmsak, Güneş, Öğle, İkindi, Akşam, Yatsı)
  internetten (Diyanet hesaplama yöntemiyle) otomatik çeker. İki ayrı
  bölümden oluşur:
  - **Günlük Vakit Sesi**: her vakit için tek bir basit ayar - açarsanız,
    vakit girdiği anda seçtiğiniz ses dosyası tam vaktinde çalınır.
    Dakika/yön gibi bir karmaşıklık yoktur; sadece aç/kapa + ses seçimi.
  - **Cuma Namazı**: öğle/Cuma vaktine göre önce ve/veya sonra tetiklenen,
    kendi bağımsız bölümü. İstediğiniz kadar kayıt ekleyebilirsiniz -
    ör. namazdan 15 dk önce paydos zili **ve** namazdan 30 dk sonra
    mesaiye/derse dönüş zili aynı anda, birbirinden bağımsız olarak
    aktif olabilir. Her kayıt için dakika, yön (önce/sonra), etiket,
    kendi ses dosyası ve etkin/pasif seçilebilir. Sadece Cuma günleri
    çalışır, diğer günler hiç tetiklenmez.
  - **Pencereyi en üstte göster**: isterseniz ana pencere diğer
    programların önünde sabit kalır.
- **Kalıcı ayarlar**: Tüm ayarlar diske kaydedilir, bilgisayar
  kapatılıp açıldığında kaldığı yerden devam eder.
- **Sistem tepsisine küçültme**: Pencereyi kapatma (X) butonuna
  bastığınızda program tamamen kapanmaz, sistem tepsisine küçülür ve
  arka planda zil çalmaya devam eder. Tamamen kapatmak için tepsi
  simgesine sağ tıklayıp "Çıkış" seçilir.
- **Windows açılışında otomatik başlatma**: Bilgisayar her açıldığında
  programın kendiliğinden başlamasını sağlayabilirsiniz.
- **Tatil günleri**: Belirlediğiniz tarihlerde (resmi/okul tatili vb.)
  hiçbir zil çalmaz.
- **Dosyaya log kaydı**: Tüm zil kayıtları, pencere kapansa bile
  incelenebilmesi için ayrıca bir log dosyasına da yazılır.

## Klasör yapısı

```
zil_takip/
  main.py              Uygulama giriş noktası
  app_window.py        Tkinter arayüzü (Zil Programı / Namaz Vakitleri / Ses Ayarları sekmeleri)
  scheduler.py         Arka planda zamanı takip edip zili/vakit bildirimini tetikleyen thread
  audio_player.py      Hoparlör listeleme ve seçilen cihazdan ses çalma (sounddevice)
  prayer_service.py    Namaz vakitlerini internetten çekme ve önbellekleme
  config_store.py      Ayarların diske (JSON) kaydedilmesi
  tray_icon.py         Sistem tepsisi simgesi ve menüsü (pystray)
  autostart.py         Windows açılışında otomatik başlatma (winreg)
  app_logging.py       Zil kayıtlarının dosyaya yazılması
  requirements.txt     Python bağımlılıkları
  zil_takip.spec       PyInstaller paketleme yapılandırması
docs/screenshots/      README'deki ekran görüntüleri
```

Ayarlar, Windows'ta `%APPDATA%\ZilTakipProgrami\config.json` dosyasında
saklanır.

## Kullanım

1. Programı ilk açtığınızda sizden çalınacak zil sesi dosyasını seçmeniz
   istenir.
2. **Zil Programı** sekmesinden düzenli zil saatlerinizi ekleyin (etiket,
   saat, günler, isteğe bağlı özel ses).
3. **Ses Ayarları** sekmesinden zilin çalınacağı hoparlörü ve ses
   seviyesini seçin.
4. **Namaz Vakitleri** sekmesinden ilinizi/ilçenizi girin, özelliği
   etkinleştirin. **Günlük Vakit Sesi** bölümünde her vakit için "Oku"
   kutucuğunu işaretleyip bir ses dosyası seçerseniz, o vakit tam saatinde
   çalar. **Cuma Namazı** bölümünde "➕ Ekle" ile öğle/Cuma vaktine göre
   önce ve/veya sonra tetiklenen istediğiniz kadar bağımsız kayıt
   ekleyebilirsiniz (ör. namazdan 15 dk önce paydos zili ve namazdan 30 dk
   sonra mesaiye dönüş zili birlikte). "Bugünün Vakitlerini Göster"
   butonuyla o günkü vakitleri anında görebilir, "Şuan ki Ayarları Kaydet"
   butonuyla değişiklikleri onaylayabilirsiniz.
5. **Genel** sekmesinden sistem tepsisine küçültmeyi, Windows'ta otomatik
   başlatmayı açıp kapatabilir, tatil günü ekleyebilirsiniz.

Program, ayarları her değişiklikte otomatik kaydeder ve arka planda
sürekli çalışarak zamanı geldiğinde zili çalar. Pencereyi kapatma (X)
butonuna basmanız sorun değil; varsayılan olarak program tamamen
kapanmaz, sistem tepsisine küçülüp arka planda çalışmaya devam eder.
Tamamen kapatmak isterseniz tepsi simgesine sağ tıklayıp "Çıkış"ı seçin.

## Windows .exe nasıl üretiliyor?

Bu proje bir Linux ortamında geliştirildi, bu yüzden `.exe` doğrudan
buradan üretilemiyor (PyInstaller çalıştığı işletim sistemine göre
paketleme yapar). Bunun yerine `.github/workflows/build-windows-exe.yml`
adında bir **GitHub Actions iş akışı** var: kod her güncellendiğinde
gerçek bir **Windows sunucusunda** otomatik derleme yapıp sonucu bir
**GitHub Release**'e ekliyor — böylece yukarıdaki indirme linki her
zaman en güncel `.exe`'yi verir, GitHub hesabı gerekmez.

### Kendi bilgisayarınızda (Windows) elle derlemek isterseniz

```powershell
cd zil_takip
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pyinstaller zil_takip.spec --noconfirm --clean
# Sonuç: zil_takip\dist\CeselsanZilTakip.exe
```

## Notlar

- Namaz vakitleri, Diyanet İşleri Başkanlığı hesaplama yöntemi kullanan
  halka açık bir servisten (Aladhan API, `method=13`) alınır; bu nedenle
  bilgisayarın internete bağlı olması gerekir. Vakitler bir kez
  alındıktan sonra o gün için önbelleğe alınır.
- Uygulamanın sürekli zil çalabilmesi için açık kalması gerekir
  (bilgisayar kapatılmamalı/uyku moduna alınmamalıdır).
- .exe imzasızdır (ücretli bir kod imzalama sertifikası gerektirir), bu
  yüzden ilk çalıştırmada Windows SmartScreen uyarısı çıkabilir - bkz.
  yukarıdaki "İndir" bölümü. SmartScreen/antivirüs tarafından yanlışlıkla
  şüpheli işaretlenme ihtimalini azaltmak için derleme UPX sıkıştırması
  kullanmaz ve exe'ye gerçek yayıncı/sürüm bilgisi (Ceselsan) gömülür.
- **Windows 7 desteklenir** (derleme, Windows 7'yi destekleyen son Python
  sürümü olan 3.8 ile yapılır). Eski/güncellenmemiş bir Windows 7'de
  uygulama "ucrtbase.dll bulunamadı" gibi bir hatayla açılmazsa, Microsoft'un
  ücretsiz **Visual C++ 2015-2022 Redistributable (x86)**'ını kurun -
  [aka.ms/vs/17/release/vc_redist.x86.exe](https://aka.ms/vs/17/release/vc_redist.x86.exe) -
  bu, Windows 7'de fabrika ayarlarıyla bulunmayan ama modern Python
  programlarının ihtiyaç duyduğu "Universal C Runtime" bileşenini kurar.
  (64-bit Windows 7 kullanıyorsanız `vc_redist.x64.exe` sürümünü kurun.)
