"""Logging utilities for ego-mcp runtime."""

from __future__ import annotations

from datetime import datetime
import json
import logging
import os
from pathlib import Path
import sys
import threading
from typing import Any

TRACE_LEVEL_NUM = 5
logging.addLevelName(TRACE_LEVEL_NUM, "TRACE")


class JsonLineFormatter(logging.Formatter):
    """Format log records as JSON Lines."""

    _reserved = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "asctime",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key in self._reserved or key.startswith("_"):
                continue
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = record.stack_info

        return json.dumps(payload, ensure_ascii=False, default=str)


def _parse_log_level(value: str | None) -> int:
    if not value:
        return logging.INFO

    normalized = value.strip().upper()
    if normalized == "TRACE":
        return TRACE_LEVEL_NUM

    level = logging.getLevelName(normalized)
    if isinstance(level, int):
        return level
    return logging.INFO


def get_log_path() -> Path:
    log_dir = Path(os.getenv("EGO_MCP_LOG_DIR", "/tmp")).expanduser()
    date_stamp = datetime.now().strftime("%Y-%m-%d")
    return log_dir / f"ego-mcp-{date_stamp}.log"


def configure_logging() -> Path:
    """Configure root logger to output JSONL logs to a configurable directory."""
    log_level = _parse_log_level(os.getenv("LOG_LEVEL", "INFO"))
    log_path = get_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(log_level)

    for handler in list(root.handlers):
        root.removeHandler(handler)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(JsonLineFormatter())
    root.addHandler(file_handler)

    logging.captureWarnings(True)
    return log_path


def install_global_exception_hooks() -> None:
    """Capture uncaught exceptions into logs."""

    def _sys_hook(exc_type: type[BaseException], exc: BaseException, tb: Any) -> None:
        logging.getLogger("ego_mcp.unhandled").error(
            "Unhandled exception",
            exc_info=(exc_type, exc, tb),
        )
        sys.__excepthook__(exc_type, exc, tb)

    def _thread_hook(args: threading.ExceptHookArgs) -> None:
        if args.exc_value is not None:
            exc_info: (
                tuple[type[BaseException], BaseException, Any]
                | tuple[None, None, None]
            ) = (args.exc_type, args.exc_value, args.exc_traceback)
        else:
            exc_info = (None, None, None)

        logging.getLogger("ego_mcp.unhandled").error(
            "Unhandled thread exception",
            exc_info=exc_info,
        )
        threading.__excepthook__(args)

    sys.excepthook = _sys_hook
    threading.excepthook = _thread_hook
