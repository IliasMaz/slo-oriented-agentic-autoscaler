"""Channel-based logging utilities for autoscaler runtime events.
"""

from __future__ import annotations

import json
import logging
import os
from logging.handlers import RotatingFileHandler

from config import LOG_BACKUP_COUNT, LOG_DIR, LOG_LEVEL, LOG_MAX_BYTES


_CHANNEL_CACHE: dict[str, logging.Logger] = {}


def _normalize_level(level_name: str) -> int:
    return getattr(logging, level_name.upper(), logging.INFO)


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

    _CHANNEL_CACHE[channel] = logger
    return logger


def log_event(
    logger: logging.Logger,
    event: str,
    title: str | None = None,
    **fields,
) -> None:
    """Log one structured event with a compact bracketed title.

    Example output:
    [error_agent:hold] {"event": "agent_recommendation", ...}
    """
    payload = {"event": event, **fields}
    label = title or event
    message = f"[{label}] {json.dumps(payload, ensure_ascii=True, default=str)}"
    logger.info(message)


def _format_key_values(**fields) -> str:
    if not fields:
        return ""
    parts = [
        f"{key}={json.dumps(value, ensure_ascii=True, default=str)}"
        for key, value in fields.items()
    ]
    return " | " + " ".join(parts)


def log_human(
    logger: logging.Logger,
    stage: str,
    message: str,
    cycle_id: int | None = None,
    **fields,
) -> None:
    """Log one human-readable line for easy run tracing."""
    cycle_tag = f"cycle={cycle_id}" if cycle_id is not None else "cycle=-"
    suffix = _format_key_values(**fields)
    logger.info(f"[{stage}] {cycle_tag} {message}{suffix}")
