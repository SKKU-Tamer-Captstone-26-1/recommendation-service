from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings


class JsonLogFormatter(logging.Formatter):
    """Small JSON formatter for structured beta operations logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        structured = getattr(record, "structured", None)
        if isinstance(structured, dict):
            payload.update(_json_safe_dict(structured))
        if record.exc_info:
            payload.setdefault("error_type", record.exc_info[0].__name__)
            payload["error"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def configure_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    if not settings.structured_logs:
        logging.basicConfig(level=level)
        logging.getLogger().setLevel(level)
        return

    formatter = JsonLogFormatter()
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    if not root_logger.handlers:
        root_logger.addHandler(logging.StreamHandler())
    for handler in root_logger.handlers:
        handler.setLevel(level)
        handler.setFormatter(formatter)


def _json_safe_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: _json_safe(value) for key, value in payload.items()}


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_safe(item) for item in value]
    return str(value)
