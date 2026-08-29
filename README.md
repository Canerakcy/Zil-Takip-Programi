# 🔔 Ceselsan Zil Takip Programı

Okul/kurum zil saatlerini otomatik olarak çalan, Windows için masaüstü
uygulaması. Kaynak kodu `zil_takip/` klasöründedir, Python + Tkinter ile
yazılmıştır.

## 📥 İndir

Kuruluma gerek yok, GitHub hesabı da gerekmiyor — aşağıdaki linke
tıklamanız yeterli:

**👉 [CeselsanZilTakip.exe indir](https://github.com/Canerakcy/Zil-Takip-Program-/releases/latest/download/CeselsanZilTakip.exe)**

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

## Özellikler

- **Haftalık zil programı**: İstediğiniz saatlerde, istediğiniz günlerde
  otomatik zil çalar (ders başlangıç/bitiş saatleri, teneffüs vb.).
- **Hoparlör seçimi**: Sesin hangi ses çıkış cihazından (hoparlör,
  kulaklık, harici ses kartı vb.) çalınacağını Ses Ayarları sekmesinden
  seçebilirsiniz.
- **Kendi ses dosyanızı seçersiniz**: Program herhangi bir zil sesi
  üretmez/içermez. İlk açılışta ve her zil kaydında istediğiniz .wav/.mp3/
  .ogg/.flac dosyasını seçmeniz istenir.
- **Cuma namazı otomatik zili (ayırt edici özellik)**: Seçtiğiniz il/ilçe
  için o haftanın Cuma/öğle namazı vaktini internetten (Diyanet
  hesaplama yöntemiyle) otomatik çeker.
  - **Namazdan önce**: uyarı zili (örn. 30 dk ve 15 dk kala).
  - **Namazdan sonra**: örneğin mesaiye/derse dönüş zili (örn. 30 dk
    sonra). Her kurumun mola süresi farklı olduğu için dakika ve yön
    (önce/sonra) tamamen sizin belirlediğiniz şekilde, istediğiniz
    kadar kayıt olarak eklenebilir.
- **Kalıcı ayarlar**: Tüm ayarlar diske kaydedilir, bilgisayar
  kapatılıp açıldığında kaldığı yerden devam eder.

## Klasör yapısı

```
zil_takip/
  main.py              Uygulama giriş noktası
  app_window.py        Tkinter arayüzü (Zil Programı / Cuma Namazı / Ses Ayarları sekmeleri)
  scheduler.py         Arka planda zamanı takip edip zili tetikleyen thread
  audio_player.py      Hoparlör listeleme ve seçilen cihazdan ses çalma (sounddevice)
  prayer_service.py    Cuma namazı vaktini internetten çekme ve önbellekleme
  config_store.py      Ayarların diske (JSON) kaydedilmesi
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
4. **Cuma Namazı** sekmesinden ilinizi/ilçenizi girin, özelliği etkinleştirin.
   Varsayılan olarak namazdan 30 dk ve 15 dk önce zil çalacak şekilde
   ayarlıdır; bu süreleri değiştirebilir, silebilir veya "namazdan sonra"
   yönünde yenilerini ekleyebilirsiniz. "Cuma Vaktini Göster" butonuyla
   o haftaki vakti anında görebilirsiniz.

Program, ayarları her değişiklikte otomatik kaydeder ve arka planda
sürekli çalışarak zamanı geldiğinde zili çalar. Pencereyi simge durumuna
küçültmeniz sorun değil (kapatmadığınız sürece çalışmaya devam eder).

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

- Cuma namazı vakti, Diyanet İşleri Başkanlığı hesaplama yöntemi
  kullanan halka açık bir namaz vakitleri servisinden (Aladhan API,
  `method=13`) alınır; bu nedenle bilgisayarın internete bağlı olması
  gerekir. Vakit bir kez alındıktan sonra o gün için önbelleğe alınır.
- Uygulamanın sürekli zil çalabilmesi için açık kalması gerekir
  (bilgisayar kapatılmamalı/uyku moduna alınmamalıdır).
