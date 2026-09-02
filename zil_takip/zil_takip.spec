# -*- mode: python ; coding: utf-8 -*-
# Ceselsan Zil Takip Programı - PyInstaller yapılandırması
# Kullanım (Windows üzerinde): pyinstaller zil_takip.spec

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'sounddevice',
        'soundfile',
        'pystray',
        'pystray._win32',
        'PIL',
        'PIL._tkinter_finder',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='CeselsanZilTakip',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX kapalı: sıkıştırılmış (packed) exe'ler, Windows SmartScreen ve
    # antivirüs yazılımları tarafından "bilinmeyen/şüpheli uygulama" olarak
    # işaretlenme ihtimali çok daha yüksek olan bir örüntüdür - imzasız bir
    # exe için bu uyarıyı azaltmanın en etkili kod tarafı adımlarından biri.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
    # Windows dosya özelliklerinde (sağ tık > Özellikler > Ayrıntılar) gerçek
    # bir yayıncı/ürün/sürüm bilgisi göstermek için (bkz. version_info.txt) -
    # imzasız bir exe'yi tamamen "güvenilir" yapmaz ama en azından kimliksiz
    # görünmesini engeller. CI'da her derlemede gerçek sürüm numarasıyla
    # yeniden üretilir (bkz. .github/workflows/build-windows-exe.yml).
    version='version_info.txt',
)
