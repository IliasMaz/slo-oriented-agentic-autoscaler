"""Channel-based logging utilities for autoscaler runtime events.
"""

from __future__ import annotations

import json
import logging
import os
from logging.handlers import RotatingFileHandler

from config import LOG_BACKUP_COUNT, LOG_DIR, LOG_LEVEL, LOG_MAX_BYTES


_CHANNEL_CACHE: dict[str, logging.Logger] = {}
_CONTROL_HANDLER: RotatingFileHandler | None = None


def _normalize_level(level_name: str) -> int:
    return getattr(logging, level_name.upper(), logging.INFO)


def _get_control_handler() -> RotatingFileHandler:
    global _CONTROL_HANDLER
    if _CONTROL_HANDLER is not None:
        return _CONTROL_HANDLER

    control_path = os.path.join(LOG_DIR, "control.log")
    handler = RotatingFileHandler(
        control_path,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    handler.setFormatter(formatter)
    _CONTROL_HANDLER = handler
    return handler


def get_channel_logger(channel: str) -> logging.Logger:
    """Return a configured logger that writes to LOG_DIR/<channel>.log."""
    cached = _CHANNEL_CACHE.get(channel)
    if cached is not None:
        return cached

    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger(f"autoscaler.{channel}")
    logger.setLevel(_normalize_level(LOG_LEVEL))
    logger.propagate = False

    if not logger.handlers:
        file_path = os.path.join(LOG_DIR, f"{channel}.log")
        handler = RotatingFileHandler(
            file_path,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.addHandler(_get_control_handler())

    _CHANNEL_CACHE[channel] = logger
    return logger


def log_event(
    logger: logging.Logger,
    event: str,
    title: str | None = None,
    **fields,
) -> None:
    """Log one structured event in a simple, timestamped, value-first format.

    Example output:
    [event] - 2026-08-13T12:30:15Z | stage=arbitration | action=scale_up | reason=throughput_pressure
    """
    label = title or event
    payload = {"event": event, **fields}
    compact = " | ".join(
        [f"{key}={json.dumps(value, ensure_ascii=True, default=str)}" for key, value in payload.items()]
    )
    logger.info(f"[{label}] - {compact}")


def _format_key_values(**fields) -> str:
    if not fields:
        return ""
    parts = [
        f"{key}={json.dumps(value, ensure_ascii=True, default=str)}"
        for key, value in fields.items()
    ]
    return " | " + " | ".join(parts)


def log_human(
    logger: logging.Logger,
    stage: str,
    message: str,
    cycle_id: int | None = None,
    **fields,
) -> None:
    """Log a human-readable line that is easy to scan during a live run."""
    cycle_tag = f"cycle={cycle_id}" if cycle_id is not None else "cycle=-"
    suffix = _format_key_values(**fields)
    logger.info(f"[{stage}] - {cycle_tag} | {message}{suffix}")
    if stage == "cycle" and message == "Cycle completed":
        logger.info("--------------------------------------------------------------------------------")
        logger.info("")


def log_exception(
    logger: logging.Logger,
    stage: str,
    cycle_id: int | None,
    exc: Exception,
    traceback_text: str,
) -> None:
    """Log a full exception payload that stays visible in .log files."""
    log_event(
        logger,
        "exception",
        title=f"exception:{stage}",
        cycle_id=cycle_id,
        error_type=type(exc).__name__,
        error=str(exc),
        traceback=traceback_text,
    )
