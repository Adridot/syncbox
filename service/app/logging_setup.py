"""Centralised logging for the Syncbox service.

The packaged app spawns the service as a frozen binary, so stdout/stderr are
only visible in the Electron console. To make a shipped app debuggable we also
write rotating log files to the platform log directory:

    macOS:  ~/Library/Logs/Syncbox/syncbox-service.log

Override the directory with RBSYNC_LOG_DIR (used by tests and dev).
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "syncbox"
_CONFIGURED = False


def default_log_dir() -> Path:
    override = os.environ.get("RBSYNC_LOG_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "Syncbox"
    # Linux/Windows fallback — keep logs next to the data dir.
    data_dir = os.environ.get("RBSYNC_DATA_DIR", ".local")
    return Path(data_dir).expanduser() / "logs"


def log_file_path() -> Path:
    return default_log_dir() / "syncbox-service.log"


def configure_logging() -> logging.Logger:
    """Idempotently configure the root + ``syncbox`` loggers."""
    global _CONFIGURED
    logger = logging.getLogger(LOGGER_NAME)
    if _CONFIGURED:
        return logger

    level_name = os.environ.get("RBSYNC_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handlers: list[logging.Handler] = []

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    handlers.append(stream)

    try:
        log_dir = default_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "syncbox-service.log",
            maxBytes=2_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    except OSError as exc:  # pragma: no cover - filesystem edge case
        stream.handle(
            logging.LogRecord(
                LOGGER_NAME, logging.WARNING, __file__, 0,
                "Could not open log file: %s", (exc,), None,
            )
        )

    root = logging.getLogger()
    root.setLevel(level)
    # Avoid duplicate handlers if uvicorn already attached some.
    for handler in handlers:
        root.addHandler(handler)

    logger.setLevel(level)
    _CONFIGURED = True
    logger.info("Logging configured at level %s -> %s", level_name, log_file_path())
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    if name:
        return logging.getLogger(f"{LOGGER_NAME}.{name}")
    return logging.getLogger(LOGGER_NAME)
