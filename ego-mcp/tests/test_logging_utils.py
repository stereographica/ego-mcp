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


class TestParseLogLevel:
    def test_empty_value_returns_info(self) -> None:
        assert logging_utils._parse_log_level("") == logging.INFO

    def test_none_returns_info(self) -> None:
        assert logging_utils._parse_log_level(None) == logging.INFO

    def test_trace_returns_custom_level(self) -> None:
        assert logging_utils._parse_log_level("TRACE") == logging_utils.TRACE_LEVEL_NUM

    def test_debug_returns_debug(self) -> None:
        assert logging_utils._parse_log_level("DEBUG") == logging.DEBUG

    def test_unknown_level_returns_info(self) -> None:
        assert logging_utils._parse_log_level("NONEXISTENT") == logging.INFO


class TestJsonLineFormatterEdgeCases:
    def test_exception_info_included(self) -> None:
        formatter = logging_utils.JsonLineFormatter()
        try:
            raise RuntimeError("test error")
        except RuntimeError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="oops",
            args=(),
            exc_info=exc_info,
        )
        payload = json.loads(formatter.format(record))
        assert "exception" in payload
        assert "RuntimeError" in payload["exception"]

    def test_stack_info_included(self) -> None:
        formatter = logging_utils.JsonLineFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="with stack",
            args=(),
            exc_info=None,
        )
        record.stack_info = "Traceback (simulated):\n  File ..."
        payload = json.loads(formatter.format(record))
        assert "stack" in payload
        assert "simulated" in payload["stack"]


class TestInstallGlobalExceptionHooks:
    def test_sys_excepthook_installed(self) -> None:
        import sys

        original = sys.excepthook
        try:
            logging_utils.install_global_exception_hooks()
            assert sys.excepthook is not original
        finally:
            sys.excepthook = original

    def test_thread_excepthook_installed(self) -> None:
        import threading

        original = threading.excepthook
        try:
            logging_utils.install_global_exception_hooks()
            assert threading.excepthook is not original
        finally:
            threading.excepthook = original

    def test_sys_hook_logs_and_calls_original(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import sys

        logged: list[str] = []

        def mock_error(msg: str, exc_info: object = None) -> None:
            logged.append(msg)

        original_calls: list[bool] = []

        def mock_original(
            exc_type: type, exc: BaseException, tb: object
        ) -> None:
            original_calls.append(True)

        monkeypatch.setattr(sys, "__excepthook__", mock_original)

        logging_utils.install_global_exception_hooks()
        hook = sys.excepthook

        try:
            raise ValueError("test")
        except ValueError:
            ei = sys.exc_info()
            logger = logging.getLogger("ego_mcp.unhandled")
            monkeypatch.setattr(logger, "error", mock_error)
            hook(ei[0], ei[1], ei[2])  # type: ignore[arg-type]

        assert "Unhandled exception" in logged
        assert original_calls

    def test_thread_hook_logs_with_exc_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import threading

        logged: list[str] = []

        def mock_error(msg: str, exc_info: object = None) -> None:
            logged.append(msg)

        original_calls: list[bool] = []

        def mock_original(args: object) -> None:
            original_calls.append(True)

        monkeypatch.setattr(threading, "__excepthook__", mock_original)

        logging_utils.install_global_exception_hooks()
        hook = threading.excepthook

        args = threading.ExceptHookArgs(
            (ValueError, ValueError("test"), None, None)
        )
        logger = logging.getLogger("ego_mcp.unhandled")
        monkeypatch.setattr(logger, "error", mock_error)
        hook(args)

        assert "Unhandled thread exception" in logged
        assert original_calls

    def test_thread_hook_logs_with_no_exc_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import threading

        logged_exc_info: list[object] = []

        def mock_error(msg: str, exc_info: object = None) -> None:
            logged_exc_info.append(exc_info)

        original_calls: list[bool] = []

        def mock_original(args: object) -> None:
            original_calls.append(True)

        monkeypatch.setattr(threading, "__excepthook__", mock_original)

        logging_utils.install_global_exception_hooks()
        hook = threading.excepthook

        args = threading.ExceptHookArgs(
            (ValueError, None, None, None)
        )
        logger = logging.getLogger("ego_mcp.unhandled")
        monkeypatch.setattr(logger, "error", mock_error)
        hook(args)

        assert logged_exc_info
        assert logged_exc_info[0] == (None, None, None)
        assert original_calls
