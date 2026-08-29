"""Ceselsan Zil Takip Programı - Giriş noktası."""
import sys
import tkinter as tk
from tkinter import messagebox

from app_window import App


def main() -> None:
    try:
        app = App()
        app.mainloop()
    except Exception as exc:  # Beklenmeyen hata durumunda kullanıcıya bilgi ver
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Ceselsan Zil Takip Programı",
                                  f"Uygulama başlatılırken hata oluştu:\n{exc}")
        finally:
            sys.exit(1)


if __name__ == "__main__":
    main()
