"""Zil kayıtlarını (ring log'larını) dosyaya da yazan, döngüsel (rotating)
log dosyası yapılandırması."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from config_store import get_app_data_dir

_logger: logging.Logger | None = None


def get_log_dir() -> Path:
    log_dir = get_app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    logger = logging.getLogger("zil_takip")
    logger.setLevel(logging.INFO)
    handler = logging.handlers.RotatingFileHandler(
        get_log_dir() / "zil_takip.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S"))
    logger.addHandler(handler)
    _logger = logger
    return logger
