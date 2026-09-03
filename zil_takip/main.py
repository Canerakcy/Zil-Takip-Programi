"""Ceselsan Zil Takip Programı - Giriş noktası."""
import sys
import tkinter as tk
from tkinter import messagebox

from app_window import App
from single_instance import SingleInstance, notify_running_instance


def main() -> None:
    instance = SingleInstance()
    if not instance.acquire():
        # Program zaten arka planda (tepside) çalışıyor - yeni bir kopya
        # açmak yerine çalışan pencereyi öne getirip çık.
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
