"""Windows açılışında otomatik başlatma + programın kapanırsa/çökerse
kendini yeniden başlatması. Sadece Windows'ta çalışır; diğer platformlarda
no-op davranır.

Sadece HKCU Run anahtarı yalnızca "oturum açılışında bir kez başlat" sağlar
- program çökerse ya da (yanlışlıkla ya da kasıtlı olarak) Görev
Yöneticisi'nden sonlandırılırsa bir daha kendiliğinden açılmaz. Bunun için
ayrıca Görev Zamanlayıcı'da "oturum açılışında başlat + her 1 dakikada bir
tekrar dene" davranışlı bir görev kaydediyoruz. schtasks'in basit (XML'siz)
/create komutu "zaten çalışıyorsa yeni örnek başlatma" politikasını
doğrudan ayarlamaya izin vermediğinden (ve bu davranış Windows sürümüne
göre değişebildiğinden), güvenlik programın KENDİSİNE bırakılıyor:
görev, exe'yi "--watchdog-check" bayrağıyla çalıştırır - main.py bu
bayrağı görüp uygulama zaten çalışıyorsa (SingleInstance kilidi, bkz.
single_instance.py) pencereyi öne getirmeden SESSİZCE çıkar, böylece 1
dakikalık denemeler zaten çalışan programı rahatsız etmez (odağı
çalmaz); program kapanmışsa (ne sebeple olursa olsun) bir sonraki
denemede normal şekilde yeniden açılır.

Bu "en iyi çaba" (best-effort) bir mekanizmadır: bilgisayarın kendisi
kapatılırsa/fişi çekilirse hiçbir yazılım bunu engelleyemez - ama
bilgisayar tekrar açıldığında (oturum açılışı tetikleyicisi sayesinde)
program yine otomatik başlar."""
from __future__ import annotations

import subprocess
import sys

RUN_KEY_NAME = "CeselsanZilTakipProgrami"
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
WATCHDOG_TASK_NAME = "CeselsanZilTakipProgrami_Watchdog"


def is_supported() -> bool:
    return sys.platform == "win32"


def is_enabled() -> bool:
    if not is_supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, RUN_KEY_NAME)
            return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    if not is_supported():
        return
    import winreg
    if enabled:
        exe_path = sys.executable
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0,
                             winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, RUN_KEY_NAME, 0, winreg.REG_SZ, f'"{exe_path}"')
        _register_watchdog_task(exe_path)
    else:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0,
                             winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, RUN_KEY_NAME)
            except OSError:
                pass
        _unregister_watchdog_task()


def _run_schtasks(args: list[str]) -> None:
    try:
        subprocess.run(["schtasks", *args], check=False, capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW)
    except OSError:
        pass


def _register_watchdog_task(exe_path: str) -> None:
    # "--watchdog-check": schtasks'in basit (XML'siz) /create komutunda
    # "zaten çalışıyorsa yeni örnek başlatma" politikasını doğrudan
    # ayarlamanın bir yolu yok - varsayılan davranış Windows sürümüne göre
    # değişebilir. Bu yüzden programın KENDİSİ bu bayrağı görürse ve zaten
    # bir örnek çalışıyorsa, pencereyi öne getirmeden (main.py) sessizce
    # çıkar - aksi halde her 1 dakikada bir gereksiz yere pencere öne
    # gelip odağı çalabilirdi.
    _run_schtasks([
        "/create", "/tn", WATCHDOG_TASK_NAME, "/tr", f'"{exe_path}" --watchdog-check',
        "/sc", "onlogon", "/rl", "limited", "/ri", "1", "/du", "9999:59", "/f",
    ])


def _unregister_watchdog_task() -> None:
    _run_schtasks(["/delete", "/tn", WATCHDOG_TASK_NAME, "/f"])
