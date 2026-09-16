"""Tests for the derived file contract and DerivedReader (D0 S2 / S3)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from ego_mcp.derived.contract import (
    DERIVED_SURFACED_MAX,
    DerivedFile,
    DerivedReader,
    lens_path,
    read_lens_file,
    write_lens_file,
)

TZ = timezone(timedelta(hours=9))
NOW = datetime(2026, 9, 16, 3, 0, 0, tzinfo=TZ)


def _file(
    lens: str = "recurrence",
    items: list[dict[str, Any]] | None = None,
    *,
    ttl_hours: float = 36.0,
) -> DerivedFile:
    return DerivedFile(
        lens=lens,
        generated_at=NOW.isoformat(),
        valid_until=(NOW + timedelta(hours=ttl_hours)).isoformat(),
        source={"memory_count": 3, "notion_count": 1, "embedding_count": 3},
        items=items if items is not None else [{"key": "recurrence:mem_a:2026-09-16"}],
    )


# --- write_lens_file --------------------------------------------------------


def test_write_lens_file_creates_directory_and_returns_path(tmp_path: Path) -> None:
    path = write_lens_file(tmp_path, _file())
    assert path == tmp_path / "derived" / "recurrence.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema"] == 1
    assert payload["lens"] == "recurrence"
    assert payload["items"] == [{"key": "recurrence:mem_a:2026-09-16"}]


def test_write_lens_file_leaves_no_temp_file(tmp_path: Path) -> None:
    write_lens_file(tmp_path, _file())
    leftovers = [p.name for p in (tmp_path / "derived").iterdir() if p.name.startswith(".")]
    assert leftovers == []


def test_write_lens_file_is_atomic_on_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed replace leaves the previous file intact and no temp behind."""
    write_lens_file(tmp_path, _file(items=[{"key": "old"}]))
    before = (tmp_path / "derived" / "recurrence.json").read_bytes()

    def _boom(src: Any, dst: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("ego_mcp.derived.contract.os.replace", _boom)
    with pytest.raises(OSError):
        write_lens_file(tmp_path, _file(items=[{"key": "new"}]))

    assert (tmp_path / "derived" / "recurrence.json").read_bytes() == before
    leftovers = [p.name for p in (tmp_path / "derived").iterdir() if p.name.startswith(".")]
    assert leftovers == []


def test_write_lens_file_does_not_create_target_when_serialization_fails(
    tmp_path: Path,
) -> None:
    bad = DerivedFile(
        lens="recurrence",
        generated_at=NOW.isoformat(),
        valid_until=(NOW + timedelta(hours=1)).isoformat(),
        source={},
        items=[{"key": "a", "value": object()}],
    )
    with pytest.raises(TypeError):
        write_lens_file(tmp_path, bad)
    assert not (tmp_path / "derived" / "recurrence.json").exists()
    assert list((tmp_path / "derived").iterdir()) == []


# --- read_lens_file failure modes ------------------------------------------


def test_read_lens_file_roundtrip(tmp_path: Path) -> None:
    write_lens_file(tmp_path, _file())
    result = read_lens_file(tmp_path, "recurrence", now=NOW)
    assert result is not None
    assert result.lens == "recurrence"
    assert result.source == {"memory_count": 3, "notion_count": 1, "embedding_count": 3}
    assert [item["key"] for item in result.items] == ["recurrence:mem_a:2026-09-16"]


def test_read_lens_file_missing_returns_none(tmp_path: Path) -> None:
    assert read_lens_file(tmp_path, "recurrence", now=NOW) is None


def _write_raw(tmp_path: Path, lens: str, text: str) -> None:
    path = lens_path(tmp_path, lens)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("{not json", id="broken_json"),
        pytest.param("[1, 2, 3]", id="not_an_object"),
        pytest.param(
            json.dumps({"schema": 2, "lens": "recurrence", "valid_until": "2099-01-01T00:00:00+09:00", "items": []}),
            id="schema_mismatch",
        ),
        pytest.param(
            json.dumps({"schema": 1, "lens": "dreams", "valid_until": "2099-01-01T00:00:00+09:00", "items": []}),
            id="lens_mismatch",
        ),
        pytest.param(
            json.dumps({"schema": 1, "lens": "recurrence", "valid_until": "not-a-date", "items": []}),
            id="unparsable_valid_until",
        ),
        pytest.param(
            json.dumps({"schema": 1, "lens": "recurrence", "items": []}),
            id="missing_valid_until",
        ),
        pytest.param(
            json.dumps({"schema": 1, "lens": "recurrence", "valid_until": "2026-09-16T02:00:00+09:00", "items": []}),
            id="expired",
        ),
        pytest.param(
            json.dumps({"schema": 1, "lens": "recurrence", "valid_until": "2099-01-01T00:00:00+09:00", "items": {}}),
            id="items_not_a_list",
        ),
    ],
)
def test_read_lens_file_returns_none_without_raising(tmp_path: Path, raw: str) -> None:
    _write_raw(tmp_path, "recurrence", raw)
    assert read_lens_file(tmp_path, "recurrence", now=NOW) is None


def test_read_lens_file_expiry_boundary_is_exclusive(tmp_path: Path) -> None:
    _write_raw(
        tmp_path,
        "recurrence",
        json.dumps(
            {
                "schema": 1,
                "lens": "recurrence",
                "valid_until": NOW.isoformat(),
                "items": [],
            }
        ),
    )
    assert read_lens_file(tmp_path, "recurrence", now=NOW) is None


def test_read_lens_file_skips_bad_items_individually(tmp_path: Path) -> None:
    _write_raw(
        tmp_path,
        "recurrence",
        json.dumps(
            {
                "schema": 1,
                "lens": "recurrence",
                "generated_at": NOW.isoformat(),
                "valid_until": (NOW + timedelta(hours=5)).isoformat(),
                "source": {"memory_count": 1},
                "items": ["nope", 7, {"no_key": 1}, {"key": ""}, {"key": 5}, {"key": "ok"}],
            }
        ),
    )
    result = read_lens_file(tmp_path, "recurrence", now=NOW)
    assert result is not None
    assert [item["key"] for item in result.items] == ["ok"]


def test_read_lens_file_is_unreadable_directory_safe(tmp_path: Path) -> None:
    path = lens_path(tmp_path, "recurrence")
    path.mkdir(parents=True)
    assert read_lens_file(tmp_path, "recurrence", now=NOW) is None


# --- DerivedReader ----------------------------------------------------------


def test_reader_items_preserve_file_order(tmp_path: Path) -> None:
    write_lens_file(
        tmp_path,
        _file(items=[{"key": "c"}, {"key": "a"}, {"key": "b"}]),
    )
    reader = DerivedReader(tmp_path)
    assert [item["key"] for item in reader.items("recurrence", now=NOW)] == ["c", "a", "b"]


def test_reader_items_exclude_surfaced(tmp_path: Path) -> None:
    write_lens_file(tmp_path, _file(items=[{"key": "a"}, {"key": "b"}, {"key": "c"}]))
    reader = DerivedReader(tmp_path)
    reader.mark_surfaced("b", now=NOW)
    assert [item["key"] for item in reader.items("recurrence", now=NOW)] == ["a", "c"]
    assert [
        item["key"]
        for item in reader.items("recurrence", now=NOW, exclude_surfaced=False)
    ] == ["a", "b", "c"]


def test_reader_items_collapse_duplicate_keys_last_value_wins(tmp_path: Path) -> None:
    write_lens_file(
        tmp_path,
        _file(items=[{"key": "a", "n": 1}, {"key": "b"}, {"key": "a", "n": 2}]),
    )
    items = DerivedReader(tmp_path).items("recurrence", now=NOW)
    assert [item["key"] for item in items] == ["a", "b"]
    assert items[0]["n"] == 2


def test_reader_items_empty_when_file_missing(tmp_path: Path) -> None:
    assert DerivedReader(tmp_path).items("recurrence", now=NOW) == []


def test_reader_is_surfaced_and_mark(tmp_path: Path) -> None:
    reader = DerivedReader(tmp_path)
    assert reader.is_surfaced("k") is False
    reader.mark_surfaced("k", now=NOW)
    assert DerivedReader(tmp_path).is_surfaced("k") is True


def test_reader_marks_file_shape(tmp_path: Path) -> None:
    reader = DerivedReader(tmp_path)
    reader.mark_surfaced("k", now=NOW)
    payload = json.loads(reader.surfaced_path.read_text(encoding="utf-8"))
    assert payload == {"schema": 1, "marks": {"k": NOW.isoformat()}}


def test_reader_mark_surfaced_caps_and_evicts_oldest(tmp_path: Path) -> None:
    reader = DerivedReader(tmp_path)
    marks = {
        f"k{i:05d}": (NOW + timedelta(seconds=i)).isoformat()
        for i in range(DERIVED_SURFACED_MAX)
    }
    reader.surfaced_path.parent.mkdir(parents=True, exist_ok=True)
    reader.surfaced_path.write_text(
        json.dumps({"schema": 1, "marks": marks}), encoding="utf-8"
    )

    reader.mark_surfaced("newest", now=NOW + timedelta(days=1))
    stored = json.loads(reader.surfaced_path.read_text(encoding="utf-8"))["marks"]
    assert len(stored) == DERIVED_SURFACED_MAX
    assert "newest" in stored
    assert "k00000" not in stored
    assert "k00001" in stored


def test_reader_corrupt_surfaced_file_reads_as_empty_and_is_overwritten(
    tmp_path: Path,
) -> None:
    reader = DerivedReader(tmp_path)
    reader.surfaced_path.parent.mkdir(parents=True, exist_ok=True)
    reader.surfaced_path.write_text("{oops", encoding="utf-8")

    assert reader.is_surfaced("anything") is False
    assert reader.marks() == {}
    reader.mark_surfaced("k", now=NOW)
    assert json.loads(reader.surfaced_path.read_text(encoding="utf-8")) == {
        "schema": 1,
        "marks": {"k": NOW.isoformat()},
    }


def test_reader_surfaced_file_with_wrong_shape_reads_as_empty(tmp_path: Path) -> None:
    reader = DerivedReader(tmp_path)
    reader.surfaced_path.parent.mkdir(parents=True, exist_ok=True)
    reader.surfaced_path.write_text(json.dumps({"marks": [1, 2]}), encoding="utf-8")
    assert reader.marks() == {}


def test_has_surfaced_with_prefix(tmp_path: Path) -> None:
    reader = DerivedReader(tmp_path)
    reader.mark_surfaced("recurrence:mem_a:2026-09-16", now=NOW)
    assert reader.has_surfaced_with_prefix("recurrence:") is True
    assert reader.has_surfaced_with_prefix("recurrence:", suffix=":2026-09-16") is True
    assert reader.has_surfaced_with_prefix("recurrence:", suffix=":2026-09-17") is False
    assert reader.has_surfaced_with_prefix("dreams:") is False


def test_has_surfaced_with_prefix_requires_both_ends(tmp_path: Path) -> None:
    reader = DerivedReader(tmp_path)
    reader.mark_surfaced("dreams:mem_a:2026-09-16", now=NOW)
    assert reader.has_surfaced_with_prefix("recurrence:", suffix=":2026-09-16") is False


def test_last_surfaced_at(tmp_path: Path) -> None:
    reader = DerivedReader(tmp_path)
    reader.mark_surfaced("drift:notion_a:w1", now=NOW)
    reader.mark_surfaced("drift:notion_a:w2", now=NOW + timedelta(days=3))
    reader.mark_surfaced("drift:notion_b:w1", now=NOW + timedelta(days=9))

    assert reader.last_surfaced_at("drift:notion_a") == NOW + timedelta(days=3)
    assert reader.last_surfaced_at("drift:notion_b") == NOW + timedelta(days=9)
    assert reader.last_surfaced_at("drift:notion_c") is None


def test_last_surfaced_at_ignores_unparsable_stamps(tmp_path: Path) -> None:
    reader = DerivedReader(tmp_path)
    reader.surfaced_path.parent.mkdir(parents=True, exist_ok=True)
    reader.surfaced_path.write_text(
        json.dumps(
            {
                "schema": 1,
                "marks": {"drift:n:a": "zzz", "drift:n:b": NOW.isoformat()},
            }
        ),
        encoding="utf-8",
    )
    assert reader.last_surfaced_at("drift:n") == NOW
