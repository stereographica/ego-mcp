"""Tests for the derived batch CLI (D0 S7)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from ego_mcp.derived import cli, lenses
from ego_mcp.derived.cli import (
    EXIT_BAD_ARGS,
    EXIT_LENS_FAILED,
    EXIT_NO_SNAPSHOT,
    EXIT_OK,
    main,
)
from ego_mcp.derived.config import DerivedConfig
from ego_mcp.derived.lenses import LENSES, register_lens
from ego_mcp.derived.source import SnapshotUnavailable, SourceSnapshot

TZ = timezone(timedelta(hours=9))
NOW = datetime(2026, 9, 16, 3, 0, 0, tzinfo=TZ)


class StubLens:
    """A registrable lens whose behaviour each test picks."""

    def __init__(
        self,
        name: str,
        *,
        items: list[dict[str, Any]] | None = None,
        needs_embeddings: bool = False,
        ttl_hours: float = 36.0,
        raises: bool = False,
        stats: dict[str, int] | None = None,
    ) -> None:
        self.name = name
        self.needs_embeddings = needs_embeddings
        self.ttl_hours = ttl_hours
        self._items = items if items is not None else [{"key": f"{name}:1"}]
        self._raises = raises
        self.stats: dict[str, int] = stats if stats is not None else {}
        self.calls = 0

    def compute(self, snapshot: SourceSnapshot) -> list[dict[str, Any]]:
        self.calls += 1
        if self._raises:
            raise RuntimeError("lens exploded")
        return list(self._items)


def _snapshot(now: datetime = NOW) -> SourceSnapshot:
    return SourceSnapshot(
        now=now,
        memories=[],
        embeddings=None,
        notions=[],
        question_log=[],
        relationships={},
        surfaced={},
        co_retrievals=[],
    )


@pytest.fixture(autouse=True)
def _clean_registry() -> Any:
    saved = dict(LENSES)
    LENSES.clear()
    yield
    LENSES.clear()
    LENSES.update(saved)


@pytest.fixture(autouse=True)
def _quiet_logging(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "configure_logging", lambda: tmp_path / "log")


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "data"
    path.mkdir()
    monkeypatch.setenv("EGO_MCP_DATA_DIR", str(path))
    monkeypatch.delenv("EGO_MCP_TIMEZONE", raising=False)
    return path


@pytest.fixture
def snapshots(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record load_snapshot calls and return a canned snapshot."""
    calls: list[dict[str, Any]] = []

    def _load(
        path: Path, *, with_embeddings: bool, now: datetime | None = None
    ) -> SourceSnapshot:
        calls.append({"data_dir": path, "with_embeddings": with_embeddings, "now": now})
        return _snapshot(now or NOW)

    monkeypatch.setattr(cli, "load_snapshot", _load)
    return calls


def _derived(data_dir: Path) -> Path:
    return data_dir / "derived"


# --- --list -----------------------------------------------------------------


def test_list_prints_lenses_and_writes_nothing(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    register_lens(StubLens("recurrence", needs_embeddings=False, ttl_hours=36.0))
    register_lens(StubLens("dreams", needs_embeddings=True, ttl_hours=12.5))

    assert main(["--list"]) == EXIT_OK

    out = capsys.readouterr().out
    assert "recurrence\tneeds_embeddings=False\tttl_hours=36.0" in out
    assert "dreams\tneeds_embeddings=True\tttl_hours=12.5" in out
    assert not _derived(data_dir).exists()


def test_list_with_empty_registry(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--list"]) == EXIT_OK
    assert "No lenses registered." in capsys.readouterr().out


def test_list_does_not_take_a_snapshot(
    data_dir: Path, snapshots: list[dict[str, Any]]
) -> None:
    register_lens(StubLens("recurrence"))
    main(["--list"])
    assert snapshots == []


# --- --dry-run --------------------------------------------------------------


def test_dry_run_prints_counts_and_writes_nothing(
    data_dir: Path,
    snapshots: list[dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    lens = StubLens(
        "recurrence",
        items=[{"key": f"recurrence:{i}"} for i in range(5)],
    )
    register_lens(lens)

    assert main(["--dry-run"]) == EXIT_OK

    out = capsys.readouterr().out
    assert "recurrence: 5 item(s)" in out
    assert "recurrence:0, recurrence:1, recurrence:2" in out
    assert "recurrence:3" not in out
    assert not _derived(data_dir).exists()
    assert lens.calls == 1


def test_dry_run_with_no_items(
    data_dir: Path,
    snapshots: list[dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    register_lens(StubLens("recurrence", items=[]))
    assert main(["--dry-run"]) == EXIT_OK
    assert "recurrence: 0 item(s)" in capsys.readouterr().out
    assert not _derived(data_dir).exists()


# --- writing ----------------------------------------------------------------


def test_run_writes_one_file_per_lens(
    data_dir: Path, snapshots: list[dict[str, Any]]
) -> None:
    register_lens(StubLens("recurrence", items=[{"key": "recurrence:a"}]))
    register_lens(StubLens("dreams", items=[{"key": "dreams:a"}], ttl_hours=12.0))

    assert main([]) == EXIT_OK

    recurrence = json.loads(
        (_derived(data_dir) / "recurrence.json").read_text(encoding="utf-8")
    )
    assert recurrence["schema"] == 1
    assert recurrence["lens"] == "recurrence"
    assert recurrence["items"] == [{"key": "recurrence:a"}]
    assert recurrence["source"] == {
        "memory_count": 0,
        "notion_count": 0,
        "embedding_count": 0,
    }

    generated_at = datetime.fromisoformat(recurrence["generated_at"])
    valid_until = datetime.fromisoformat(recurrence["valid_until"])
    assert valid_until - generated_at == timedelta(hours=36)

    dreams = json.loads((_derived(data_dir) / "dreams.json").read_text(encoding="utf-8"))
    assert datetime.fromisoformat(dreams["valid_until"]) - datetime.fromisoformat(
        dreams["generated_at"]
    ) == timedelta(hours=12)


def test_data_dir_argument_overrides_the_environment(
    data_dir: Path, snapshots: list[dict[str, Any]], tmp_path: Path
) -> None:
    override = tmp_path / "elsewhere"
    register_lens(StubLens("recurrence"))

    assert main(["--data-dir", str(override)]) == EXIT_OK

    assert (override / "derived" / "recurrence.json").exists()
    assert not _derived(data_dir).exists()
    assert snapshots[0]["data_dir"] == override


def test_lens_selection_runs_only_the_named_lenses(
    data_dir: Path, snapshots: list[dict[str, Any]]
) -> None:
    first = register_lens(StubLens("recurrence"))
    second = register_lens(StubLens("dreams"))

    assert main(["--lens", "dreams"]) == EXIT_OK

    assert isinstance(first, StubLens) and first.calls == 0
    assert isinstance(second, StubLens) and second.calls == 1
    assert not (_derived(data_dir) / "recurrence.json").exists()
    assert (_derived(data_dir) / "dreams.json").exists()


def test_lens_selection_accepts_a_comma_list(
    data_dir: Path, snapshots: list[dict[str, Any]]
) -> None:
    register_lens(StubLens("recurrence"))
    register_lens(StubLens("dreams"))
    register_lens(StubLens("holes"))

    assert main(["--lens", "recurrence, holes"]) == EXIT_OK
    assert (_derived(data_dir) / "recurrence.json").exists()
    assert (_derived(data_dir) / "holes.json").exists()
    assert not (_derived(data_dir) / "dreams.json").exists()


# --- embeddings gating ------------------------------------------------------


def test_embeddings_are_loaded_only_when_a_selected_lens_needs_them(
    data_dir: Path, snapshots: list[dict[str, Any]]
) -> None:
    register_lens(StubLens("recurrence", needs_embeddings=False))
    register_lens(StubLens("dreams", needs_embeddings=True))

    main(["--lens", "recurrence"])
    assert snapshots[-1]["with_embeddings"] is False

    main(["--lens", "dreams"])
    assert snapshots[-1]["with_embeddings"] is True

    main([])
    assert snapshots[-1]["with_embeddings"] is True


# --- exit codes -------------------------------------------------------------


def test_unknown_lens_exits_one(
    data_dir: Path,
    snapshots: list[dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    register_lens(StubLens("recurrence"))

    with pytest.raises(SystemExit) as excinfo:
        main(["--lens", "nope"])

    assert excinfo.value.code == EXIT_BAD_ARGS
    assert "Unknown lens: 'nope'" in capsys.readouterr().err
    assert snapshots == []
    assert not _derived(data_dir).exists()


def test_invalid_timezone_exits_one(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EGO_MCP_TIMEZONE", "Mars/Olympus")
    register_lens(StubLens("recurrence"))
    with pytest.raises(SystemExit) as excinfo:
        main([])
    assert excinfo.value.code == EXIT_BAD_ARGS


def test_snapshot_unavailable_exits_two_and_writes_nothing(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    register_lens(StubLens("recurrence"))

    def _boom(path: Path, *, with_embeddings: bool, now: Any = None) -> SourceSnapshot:
        raise SnapshotUnavailable("chroma is busy")

    monkeypatch.setattr(cli, "load_snapshot", _boom)

    assert main([]) == EXIT_NO_SNAPSHOT
    assert not _derived(data_dir).exists()


def test_failing_lens_exits_three_and_others_are_written(
    data_dir: Path, snapshots: list[dict[str, Any]]
) -> None:
    register_lens(StubLens("recurrence", raises=True))
    register_lens(StubLens("dreams", items=[{"key": "dreams:a"}]))

    assert main([]) == EXIT_LENS_FAILED

    assert not (_derived(data_dir) / "recurrence.json").exists()
    assert (_derived(data_dir) / "dreams.json").exists()


def test_failing_lens_leaves_the_previous_file_untouched(
    data_dir: Path, snapshots: list[dict[str, Any]]
) -> None:
    good = StubLens("recurrence", items=[{"key": "recurrence:old"}])
    register_lens(good)
    assert main([]) == EXIT_OK
    before = (_derived(data_dir) / "recurrence.json").read_bytes()

    LENSES.clear()
    register_lens(StubLens("recurrence", raises=True))
    assert main([]) == EXIT_LENS_FAILED
    assert (_derived(data_dir) / "recurrence.json").read_bytes() == before


# --- logging ----------------------------------------------------------------


def test_completion_log_carries_the_documented_extra(
    data_dir: Path,
    snapshots: list[dict[str, Any]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    register_lens(
        StubLens(
            "dreams",
            items=[{"key": "dreams:a"}, {"key": "dreams:b"}],
            stats={"dream_pairs_linked": 3},
        )
    )

    with caplog.at_level(logging.INFO, logger="ego_mcp.derived"):
        assert main([]) == EXIT_OK

    records = [r for r in caplog.records if r.message == "Derived lens completed"]
    assert len(records) == 1
    record = records[0]
    assert record.__dict__["lens"] == "dreams"
    assert record.__dict__["item_count"] == 2
    assert record.__dict__["memory_count"] == 0
    assert record.__dict__["embedding_count"] == 0
    assert isinstance(record.__dict__["duration_ms"], int)
    assert record.__dict__["dream_pairs_linked"] == 3


def test_failure_log_message_and_exc_info(
    data_dir: Path,
    snapshots: list[dict[str, Any]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    register_lens(StubLens("recurrence", raises=True))

    with caplog.at_level(logging.ERROR, logger="ego_mcp.derived"):
        assert main([]) == EXIT_LENS_FAILED

    records = [r for r in caplog.records if r.message == "Derived lens failed"]
    assert len(records) == 1
    assert records[0].exc_info is not None
    assert records[0].__dict__["lens"] == "recurrence"


def test_configure_logging_is_called(
    data_dir: Path, snapshots: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[bool] = []
    monkeypatch.setattr(cli, "configure_logging", lambda: called.append(True))
    register_lens(StubLens("recurrence"))
    main([])
    assert called == [True]


# --- registry ---------------------------------------------------------------


def test_register_lens_rejects_bad_names() -> None:
    for bad in ("Recurrence", "co-retrieval", "lens1", "", "co retrieval"):
        with pytest.raises(ValueError):
            register_lens(StubLens(bad))


def test_register_lens_rejects_duplicates() -> None:
    register_lens(StubLens("recurrence"))
    with pytest.raises(ValueError):
        register_lens(StubLens("recurrence"))


def test_registry_starts_empty_without_a_registry_module() -> None:
    lenses.discover_lenses()
    assert LENSES == {}


def test_lens_stats_ignores_non_integer_values() -> None:
    lens = StubLens("recurrence")
    lens.stats = {"ok": 2, "bad": "x", "flag": True}  # type: ignore[dict-item]
    assert lenses.lens_stats(lens) == {"ok": 2}


def test_lens_stats_of_a_lens_without_stats() -> None:
    class Bare:
        name = "bare"
        needs_embeddings = False
        ttl_hours = 1.0

        def compute(self, snapshot: SourceSnapshot) -> list[dict[str, Any]]:
            return []

    assert lenses.lens_stats(Bare()) == {}


# --- DerivedConfig ----------------------------------------------------------


def test_derived_config_reads_data_dir_and_timezone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("EGO_MCP_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("EGO_MCP_TIMEZONE", "Asia/Tokyo")
    config = DerivedConfig.from_env()
    assert config.data_dir == tmp_path / "d"
    assert config.timezone == "Asia/Tokyo"


def test_derived_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EGO_MCP_DATA_DIR", raising=False)
    monkeypatch.delenv("EGO_MCP_TIMEZONE", raising=False)
    config = DerivedConfig.from_env()
    assert config.data_dir == Path.home() / ".ego-mcp" / "data"
    assert config.timezone == "UTC"


def test_derived_config_needs_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert DerivedConfig.from_env().timezone


def test_derived_config_rejects_an_unknown_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EGO_MCP_TIMEZONE", "Mars/Olympus")
    with pytest.raises(ValueError, match="Invalid timezone 'Mars/Olympus'"):
        DerivedConfig.from_env()
