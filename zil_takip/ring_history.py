"""Zil çalma geçmişini (istatistikler için) diske kaydeden/okuyan yardımcı
modül. JSON Lines (.jsonl) formatında - her satır bağımsız bir olay, dosya
sonuna eklenir. Program yıllarca kapatılmadan çalışabileceği için dosya
sınırsız büyümesin diye belirli bir boyutu aşınca en son N kayda kırpılır."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from config_store import get_app_data_dir

HISTORY_FILE_NAME = "ring_history.jsonl"
MAX_ENTRIES = 5000
TRIM_CHECK_BYTES = 5_000_000


def get_history_path() -> Path:
    return get_app_data_dir() / HISTORY_FILE_NAME


def record_ring(label: str, kind: str, success: bool = True,
                 error: Optional[str] = None) -> None:
    """Bir zil çalma olayını kalıcı geçmişe ekler (İstatistikler sekmesinde
    gösterilir). Bu asla zilin çalmasını engellememeli/geciktirmemeli - yazma
    hatası sessizce yutulur."""
    entry: dict[str, Any] = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "label": label,
        "kind": kind,
        "success": success,
    }
    if error:
        entry["error"] = error
    try:
        path = get_history_path()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        _trim_if_needed(path)
    except OSError:
        pass


def _trim_if_needed(path: Path) -> None:
    try:
        if path.stat().st_size < TRIM_CHECK_BYTES:
            return
    except OSError:
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return
    if len(lines) <= MAX_ENTRIES:
        return
    trimmed = lines[-MAX_ENTRIES:]
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.writelines(trimmed)
    tmp_path.replace(path)


def load_history() -> list[dict[str, Any]]:
    """Tüm geçmişi (en eskiden en yeniye) döndürür - dosya yoksa/okunamazsa
    boş liste döner."""
    path = get_history_path()
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return entries
