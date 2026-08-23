"""Structured (JSON-lines) logging to stderr.

Stdout is reserved for command output; logs therefore always go to stderr so
piping/redirection of command data stays clean.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, TextIO


class JsonlHandler(logging.Handler):
    def __init__(self, stream: TextIO | None = None) -> None:
        super().__init__()
        self.setFormatter(logging.Formatter())
        self.stream = stream or sys.stderr

    def emit(self, record: logging.LogRecord) -> None:
        timestamp = datetime.fromtimestamp(record.created, UTC).isoformat()
        entry: dict[str, Any] = {
            "ts": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info is not None:
            formatter = self.formatter
            entry["exception"] = (
                formatter.formatException(record.exc_info) if formatter is not None else None
            )
        try:
            self.stream.write(json.dumps(entry) + "\n")
            self.stream.flush()
        except Exception:  # pragma: no cover - logging safety net
            self.handleError(record)


def configure_logging(level: str = "WARNING", *, stream: TextIO | None = None) -> logging.Logger:
    logger = logging.getLogger("godotforge")
    logger.handlers.clear()
    logger.setLevel(level)
    logger.addHandler(JsonlHandler(stream=stream))
    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("godotforge")
