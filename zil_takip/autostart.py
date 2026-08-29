"""Windows açılışında otomatik başlatma (HKCU Run anahtarı).
Sadece Windows'ta çalışır; diğer platformlarda no-op davranır."""
from __future__ import annotations

import sys

RUN_KEY_NAME = "CeselsanZilTakipProgrami"
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


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
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            exe_path = sys.executable
            winreg.SetValueEx(key, RUN_KEY_NAME, 0, winreg.REG_SZ, f'"{exe_path}"')
        else:
            try:
                winreg.DeleteValue(key, RUN_KEY_NAME)
            except OSError:
                pass
