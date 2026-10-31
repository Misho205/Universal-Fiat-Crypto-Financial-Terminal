"""Structured logging without secrets or sensitive payment data."""
from __future__ import annotations

import json
import logging
import sys
from typing import Any

_SENSITIVE_KEYS = {"pan", "cvv", "pin", "secret", "api_key", "apikey", "password", "seed", "private_key", "token"}


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: ("[REDACTED]" if k.lower() in _SENSITIVE_KEYS else _redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": event, **_redact(fields)}, default=str))
