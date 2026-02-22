from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from ego_mcp import logging_utils


def test_json_line_formatter_includes_extra_fields() -> None:
    formatter = logging_utils.JsonLineFormatter()
    record = logging.LogRecord(
        name="ego_mcp.server",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Tool invocation",
        args=(),
        exc_info=None,
    )
    record.tool_name = "wake_up"
    record.tool_args = {"example": "value"}

    payload = json.loads(formatter.format(record))

    assert payload["message"] == "Tool invocation"
    assert payload["tool_name"] == "wake_up"
    assert payload["tool_args"] == {"example": "value"}


def test_json_line_formatter_uses_utc_timestamp_with_timezone() -> None:
    formatter = logging_utils.JsonLineFormatter()
    record = logging.LogRecord(
        name="ego_mcp.server",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Tool invocation",
        args=(),
        exc_info=None,
    )
    record.created = 1_700_000_000.0

    payload = json.loads(formatter.format(record))

    assert payload["timestamp"].endswith("Z")
    assert payload["timestamp"] == "2023-11-14T22:13:20Z"


def test_configure_logging_uses_log_level_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    tmp_log = Path("/tmp/ego-mcp-test.log")
    if tmp_log.exists():
        tmp_log.unlink()

    monkeypatch.setattr(logging_utils, "get_log_path", lambda: tmp_log)

    path = logging_utils.configure_logging()

    assert path == tmp_log
    assert logging.getLogger().level == logging.DEBUG
    assert tmp_log.exists()


def test_get_log_path_uses_configurable_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EGO_MCP_LOG_DIR", "/var/tmp/ego-custom")

    path = logging_utils.get_log_path()

    assert path.parent == Path("/var/tmp/ego-custom")
    assert path.name.startswith("ego-mcp-")
    assert path.suffix == ".log"
