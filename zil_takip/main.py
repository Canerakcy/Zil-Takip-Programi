"""Ceselsan Zil Takip Programı - Giriş noktası."""
import sys
import tkinter as tk
from tkinter import messagebox

from app_window import App
from single_instance import SingleInstance, notify_running_instance


def main() -> None:
    # "--watchdog-check": Görev Zamanlayıcı'nın kapanırsa/çökerse kendini
    # yeniden açma göreviyle (bkz. autostart.py) her 1 dakikada bir sessizce
    # çalıştırılır - amaç SADECE "hâlâ ayakta mı" diye yoklamaktır. Program
    # zaten çalışıyorsa burada da normal (bayraksız) açılıştaki gibi
    # pencereyi öne getirip odağı çalmak, kullanıcıyı her dakika rahatsız
    # ederdi - bu yüzden bu durumda sessizce çıkılır.
    is_watchdog_check = "--watchdog-check" in sys.argv[1:]

    instance = SingleInstance()
    if not instance.acquire():
        if not is_watchdog_check:
            # Program zaten arka planda (tepside) çalışıyor - kullanıcı
            # exe'ye tekrar tıkladı: yeni bir kopya açmak yerine çalışan
            # pencereyi öne getirip çık.
            notify_running_instance()
        return
    try:
        app = App(instance)
        app.mainloop()
    except Exception as exc:  # Beklenmeyen hata durumunda kullanıcıya bilgi ver
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Ceselsan Zil Takip Programı",
                                  f"Uygulama başlatılırken hata oluştu:\n{exc}")
        finally:
            sys.exit(1)
    finally:
        instance.close()


if __name__ == "__main__":
    main()
