# Ceselsan Zil Takip Programı

Okul/kurum zil saatlerini otomatik olarak çalan, Windows için masaüstü
uygulaması. Kaynak kodu `zil_takip/` klasöründedir, Python + Tkinter ile
yazılmıştır.

## Özellikler

- **Haftalık zil programı**: İstediğiniz saatlerde, istediğiniz günlerde
  otomatik zil çalar (ders başlangıç/bitiş saatleri, teneffüs vb.).
- **Hoparlör seçimi**: Sesin hangi ses çıkış cihazından (hoparlör,
  kulaklık, harici ses kartı vb.) çalınacağını Ses Ayarları sekmesinden
  seçebilirsiniz.
- **Kendi ses dosyanızı seçersiniz**: Program herhangi bir zil sesi
  üretmez/içermez. İlk açılışta ve her zil kaydında istediğiniz .wav/.mp3/
  .ogg/.flac dosyasını seçmeniz istenir.
- **Cuma namazı otomatik zili (fark özelliği)**: Seçtiğiniz il/ilçe için
  o haftanın Cuma/öğle namazı vaktini internetten (Diyanet hesaplama
  yöntemiyle) otomatik çeker ve namazdan **30 dakika önce** ile
  **15 dakika önce** (süreler değiştirilebilir/eklenebilir) otomatik zil
  çalar.

## Klasör yapısı

```
zil_takip/
  main.py            Uygulama giriş noktası
  app_window.py       Tkinter arayüzü (Zil Programı / Cuma Namazı / Ses Ayarları sekmeleri)
  scheduler.py         Arka planda zamanı takip edip zili tetikleyen thread
  audio_player.py      Hoparlör listeleme ve seçilen cihazdan ses çalma (sounddevice)
  prayer_service.py    Cuma namazı vaktini internetten çekme ve önbellekleme
  config_store.py      Ayarların diske (JSON) kaydedilmesi
  requirements.txt     Python bağımlılıkları
  zil_takip.spec        PyInstaller paketleme yapılandırması
```

Ayarlar, Windows'ta `%APPDATA%\ZilTakipProgrami\config.json` dosyasında
saklanır.

## Windows .exe nasıl elde edilir?

Bu proje bir Linux ortamında geliştirildiği için buradan doğrudan bir
Windows `.exe` dosyası üretilemez (PyInstaller, çalıştığı işletim
sistemine göre paketleme yapar). Bunun yerine depoya bir **GitHub
Actions iş akışı** eklendi:
`.github/workflows/build-windows-exe.yml`

Bu iş akışı, `zil_takip/` klasöründe değişiklik olduğunda (veya elle
tetiklendiğinde) GitHub'ın gerçek bir **Windows sunucusunda** otomatik
olarak çalışır, `pyinstaller` ile `CeselsanZilTakip.exe` dosyasını üretir
ve GitHub üzerinde bir "artifact" (derlenmiş dosya) olarak yükler.

**.exe'yi indirmek için:**
1. Bu depoyu GitHub'da açın → **Actions** sekmesi.
2. "Windows EXE Derle" iş akışının en son (yeşil tikli) çalışmasına tıklayın.
3. Sayfanın altındaki **Artifacts** bölümünden
   `CeselsanZilTakip-windows-exe` dosyasını indirin, içinden çıkan
   `CeselsanZilTakip.exe` dosyasını çalıştırın.

İsterseniz workflow'u elle de tetikleyebilirsiniz: Actions → "Windows EXE
Derle" → "Run workflow".

### Kendi bilgisayarınızda (Windows) elle derlemek isterseniz

```powershell
cd zil_takip
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pyinstaller zil_takip.spec --noconfirm --clean
# Sonuç: zil_takip\dist\CeselsanZilTakip.exe
```

## Kullanım

1. Programı ilk açtığınızda sizden çalınacak zil sesi dosyasını seçmeniz
   istenir.
2. **Zil Programı** sekmesinden düzenli zil saatlerinizi ekleyin (etiket,
   saat, günler, isteğe bağlı özel ses).
3. **Ses Ayarları** sekmesinden zilin çalınacağı hoparlörü ve ses
   seviyesini seçin.
4. **Cuma Namazı** sekmesinden ilinizi/ilçenizi girin, özelliği etkinleştirin.
   Varsayılan olarak namazdan 30 dk ve 15 dk önce zil çalacak şekilde
   ayarlıdır; bu süreleri değiştirebilir veya yenilerini ekleyebilirsiniz.
   "Cuma Vaktini Göster" butonuyla o haftaki vakti anında görebilirsiniz.

Program, ayarları her değişiklikte otomatik kaydeder ve arka planda
sürekli çalışarak zamanı geldiğinde zili çalar. Bilgisayar kapatılıp
tekrar açıldığında kaldığı ayarlarla devam eder.

## Notlar

- Cuma namazı vakti, Diyanet İşleri Başkanlığı hesaplama yöntemi
  kullanan halka açık bir namaz vakitleri servisinden (Aladhan API,
  `method=13`) alınır; bu nedenle bilgisayarın internete bağlı olması
  gerekir. Vakit bir kez alındıktan sonra o gün için önbelleğe alınır.
- Uygulamanın sürekli zil çalabilmesi için açık kalması gerekir
  (bilgisayar kapatılmamalı/uyku moduna alınmamalıdır).
