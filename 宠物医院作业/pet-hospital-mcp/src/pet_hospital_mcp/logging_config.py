"""JSON logging with recursive redaction of sensitive fields.

Sensitive keys (any casing/underscore spelling of ``ownerPhone``, ``ownerAddr``,
``chipNo``) are redacted recursively before they reach a log line.
"""

from __future__ import annotations

import json
import logging
from typing import Any

SENSITIVE_KEYS = frozenset({"ownerphone", "owneraddr", "chipno"})

# Fields the formatter forwards from ``extra=`` (records never carry the rest).
STRUCTURED_FIELDS = ("tool_name", "params", "status", "duration_ms")


def _normalize(key: str) -> str:
    return key.lower().replace("_", "").replace("-", "")


def redact(value: Any) -> Any:
    """Recursively replace values stored under sensitive keys with ``"***"``."""
    if isinstance(value, dict):
        return {
            k: "***" if _normalize(str(k)) in SENSITIVE_KEYS else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return type(value)(redact(item) for item in value)
    return value


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in STRUCTURED_FIELDS:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON formatter on the package logger."""
    logger = logging.getLogger("pet_hospital_mcp")
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(level.upper())
    logger.propagate = False
