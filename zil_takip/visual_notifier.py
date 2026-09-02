"""Vakit girdiğinde ekranda gösterilen görsel uyarı penceresi (Toplevel).

Tkinter pencereleri sadece ana thread'den oluşturulabildiğinden, bu modül
doğrudan zamanlayıcı (arka plan thread'i) tarafından değil, ana pencere
(app_window.App) tarafından `root.after(0, ...)` üzerinden çağrılır."""
from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

BG = "#1f4a34"
FG = "white"
AUTO_CLOSE_MS = 8000


def show_visual_notice(root: tk.Tk, title: str, subtitle: str,
                        on_dismiss: Optional[Callable[[], None]] = None) -> None:
    """Ekranın sağ üst köşesinde, kısa süre sonra kendiliğinden kapanan
    (ya da elle kapatılabilen) bir bildirim penceresi gösterir. Kapanınca
    (otomatik ya da elle) on_dismiss varsa çağrılır - "Görsel Uyandan sonra
    Ezana Devam Et" seçeneğinde sesin görselden SONRA başlaması için."""
    popup = tk.Toplevel(root)
    popup.overrideredirect(True)
    popup.attributes("-topmost", True)
    popup.configure(bg=BG)

    width, height = 340, 130
    screen_w = popup.winfo_screenwidth()
    x = screen_w - width - 24
    y = 24
    popup.geometry(f"{width}x{height}+{x}+{y}")

    frame = tk.Frame(popup, bg=BG, highlightbackground="#2f6f4f", highlightthickness=2)
    frame.pack(fill="both", expand=True)

    tk.Label(frame, text="🕌 " + title, bg=BG, fg=FG,
              font=("Segoe UI", 14, "bold")).pack(pady=(18, 4))
    tk.Label(frame, text=subtitle, bg=BG, fg="#cfe8da",
              font=("Segoe UI", 10)).pack()

    dismissed = {"done": False}

    def dismiss() -> None:
        if dismissed["done"]:
            return
        dismissed["done"] = True
        try:
            popup.destroy()
        except tk.TclError:
            pass
        if on_dismiss:
            on_dismiss()

    tk.Button(frame, text="Kapat", command=dismiss, bg="#2f6f4f", fg=FG,
              relief="flat", activebackground="#1f4a34", activeforeground=FG).pack(pady=(10, 0))
    popup.after(AUTO_CLOSE_MS, dismiss)
    popup.bind("<Button-1>", lambda e: dismiss())
