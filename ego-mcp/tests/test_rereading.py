"""Tests for D7 re-reading history (access_log recording and presentation).

Covers S1 (metadata round-trip), S2 (recording at every access point) and
S3 (the single line recall adds when a memory has been returned to in more
than one mood).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from ego_mcp import _memory_queries
from ego_mcp._memory_serialization import (
    access_log_from_json,
    memory_from_chromadb,
    memory_to_chromadb,
)
from ego_mcp.config import EgoConfig
from ego_mcp.memory import MemoryStore
from ego_mcp.types import (
    Emotion,
    EmotionalTrace,
    Memory,
    MemorySearchResult,
    Notion,
)

# ---------------------------------------------------------------------------
# S1: data structure and metadata round-trip
# ---------------------------------------------------------------------------


def test_access_log_defaults_to_empty_list() -> None:
    assert Memory().access_log == []


def test_access_log_round_trips_through_metadata() -> None:
    entries = [
        {"at": "2026-09-01T10:00:00+09:00", "mood": "anxious", "phase": "morning"},
        {"at": "2026-09-05T23:00:00+09:00", "mood": "落ち着き", "phase": "night"},
    ]
    memory = Memory(id="mem_round", content="kept", access_log=entries)

    metadata = memory_to_chromadb(memory)
    assert isinstance(metadata["access_log"], str)
    # Non-ASCII moods stay readable rather than being escaped.
    assert "落ち着き" in metadata["access_log"]

    restored = memory_from_chromadb("mem_round", "kept", metadata)
    assert restored.access_log == entries


def test_empty_access_log_serializes_to_empty_json_list() -> None:
    assert memory_to_chromadb(Memory(id="mem_empty"))["access_log"] == "[]"


def test_memory_without_access_log_metadata_loads_as_empty() -> None:
    """Memories written before D7 carry no access_log key at all."""
    legacy = {
        "timestamp": "2026-01-01T00:00:00+09:00",
        "category": "daily",
        "emotion": "neutral",
        "access_count": 7,
    }
    restored = memory_from_chromadb("mem_legacy", "old", legacy)
    assert restored.access_log == []
    assert restored.access_count == 7


@pytest.mark.parametrize(
    "raw",
    ["", "not json", "{}", '"a string"', "42", None, 17, ["already", "a", "list"]],
)
def test_malformed_access_log_degrades_to_empty(raw: Any) -> None:
    assert access_log_from_json(raw) == []


def test_access_log_entries_are_normalized_to_strings() -> None:
    raw = json.dumps(
        [
            "not a dict",
            {"at": 123, "mood": None, "phase": ["odd"]},
            {"at": "2026-09-01T10:00:00+09:00"},
        ]
    )
    parsed = access_log_from_json(raw)
    assert len(parsed) == 2
    for entry in parsed:
        assert set(entry) == {"at", "mood", "phase"}
        assert all(isinstance(value, str) for value in entry.values())
    assert parsed[1] == {"at": "2026-09-01T10:00:00+09:00", "mood": "", "phase": ""}


def test_local_chromadb_update_round_trips_access_log() -> None:
    from ego_mcp.local_chromadb import Collection

    collection = Collection(embedding_function=lambda docs: [[1.0, 0.0] for _ in docs])
    collection.add(
        ids=["mem_local"],
        documents=["a memory"],
        metadatas=[memory_to_chromadb(Memory(id="mem_local", content="a memory"))],
    )
    entries = [{"at": "2026-09-16T09:00:00+09:00", "mood": "calm", "phase": "morning"}]
    collection.update(
        ids=["mem_local"],
        metadatas=[{"access_log": json.dumps(entries, ensure_ascii=False)}],
    )

    got = collection.get(ids=["mem_local"], include=["documents", "metadatas"])
    restored = memory_from_chromadb(
        "mem_local", got["documents"][0], got["metadatas"][0]
    )
    assert restored.access_log == entries


# ---------------------------------------------------------------------------
# S2: recording
# ---------------------------------------------------------------------------


class _RecordingCollection:
    def __init__(self, rows: list[tuple[str, str, dict[str, Any], float]]) -> None:
        self.rows = rows
        self.updated: list[tuple[list[str], list[dict[str, Any]]]] = []

    def count(self) -> int:
        return len(self.rows)

    def query(
        self,
        *,
        query_texts: list[str],
        n_results: int,
        include: list[str],
        where: dict[str, Any] | None = None,
    ) -> dict[str, list[list[Any]]]:
        del query_texts, where
        assert include == ["documents", "metadatas", "distances"]
        selected = self.rows[:n_results]
        return {
            "ids": [[row[0] for row in selected]],
            "documents": [[row[1] for row in selected]],
            "metadatas": [[row[2] for row in selected]],
            "distances": [[row[3] for row in selected]],
        }

    def update(self, *, ids: list[str], metadatas: list[dict[str, Any]]) -> None:
        self.updated.append((ids, metadatas))


class _RecordingStore:
    def __init__(self, rows: list[tuple[str, str, dict[str, Any], float]]) -> None:
        self._collection = _RecordingCollection(rows)
        self._last_recall_metadata: dict[str, object] = {}

    def _ensure_connected(self) -> _RecordingCollection:
        return self._collection


def _row(
    memory_id: str,
    *,
    distance: float = 0.05,
    timestamp: str = "2024-01-01T00:00:00+00:00",
) -> tuple[str, str, dict[str, Any], float]:
    return (
        memory_id,
        f"content of {memory_id}",
        {
            "timestamp": timestamp,
            "category": "daily",
            "emotion": "neutral",
            "intensity": 0.5,
            "valence": 0.0,
            "arousal": 0.5,
            "importance": 3,
            "access_count": 0,
        },
        distance,
    )


def _result(memory: Memory) -> MemorySearchResult:
    return MemorySearchResult(memory=memory, distance=0.1, score=0.1, decay=0.9)


@pytest.mark.asyncio
async def test_increment_access_metadata_records_mood_and_phase() -> None:
    store = _RecordingStore([_row("mem_a")])
    memory = Memory(id="mem_a", content="x")

    await _memory_queries._increment_access_metadata(
        cast(Any, store),
        [_result(memory)],
        access_mood="anxious",
        now=datetime(2026, 9, 16, 2, 0, 0),
    )

    assert len(memory.access_log) == 1
    entry = memory.access_log[0]
    assert entry["mood"] == "anxious"
    assert entry["phase"] == "late_night"
    assert entry["at"] == memory.last_accessed
    assert memory.access_count == 1

    ids, metadatas = store._collection.updated[0]
    assert ids == ["mem_a"]
    assert json.loads(metadatas[0]["access_log"]) == memory.access_log


@pytest.mark.asyncio
async def test_increment_access_metadata_without_mood_records_empty_string() -> None:
    store = _RecordingStore([_row("mem_a")])
    memory = Memory(id="mem_a", content="x")

    await _memory_queries._increment_access_metadata(cast(Any, store), [_result(memory)])

    assert memory.access_log[0]["mood"] == ""


@pytest.mark.asyncio
async def test_access_log_is_capped_fifo() -> None:
    store = _RecordingStore([_row("mem_a")])
    memory = Memory(
        id="mem_a",
        content="x",
        access_log=[
            {"at": f"2026-01-{day:02d}T00:00:00+09:00", "mood": "calm", "phase": "night"}
            for day in range(1, 13)
        ],
    )
    oldest = memory.access_log[0]

    await _memory_queries._increment_access_metadata(
        cast(Any, store), [_result(memory)], access_mood="grateful"
    )

    assert len(memory.access_log) == _memory_queries.ACCESS_LOG_MAX == 12
    assert oldest not in memory.access_log
    assert memory.access_log[-1]["mood"] == "grateful"


@pytest.mark.asyncio
async def test_repeated_memory_in_one_result_set_logs_once() -> None:
    store = _RecordingStore([_row("mem_a")])
    memory = Memory(id="mem_a", content="x")

    await _memory_queries._increment_access_metadata(
        cast(Any, store),
        [_result(memory), _result(memory)],
        access_mood="calm",
    )

    assert len(memory.access_log) == 1


@pytest.mark.asyncio
async def test_find_resurfacing_memories_records_access_mood() -> None:
    store = _RecordingStore([_row("mem_dormant", timestamp="2020-01-01T00:00:00+00:00")])

    resurfacing = await _memory_queries.find_resurfacing_memories(
        cast(Any, store), "content of mem_dormant", access_mood="melancholy"
    )

    assert [r.memory.id for r in resurfacing] == ["mem_dormant"]
    assert resurfacing[0].memory.access_log[-1]["mood"] == "melancholy"


@pytest.mark.asyncio
async def test_recall_with_explicit_filters_records_access_mood() -> None:
    store = _RecordingStore([_row("mem_a")])

    results = await _memory_queries.recall(
        cast(Any, store),
        "content of mem_a",
        n_results=1,
        category_filter="daily",
        access_mood="hopeful",
    )

    assert [r.memory.id for r in results] == ["mem_a"]
    assert results[0].memory.access_log[-1]["mood"] == "hopeful"


@pytest.mark.asyncio
async def test_search_does_not_record_an_access() -> None:
    store = _RecordingStore([_row("mem_a")])

    results = await _memory_queries.search(cast(Any, store), "content of mem_a")

    assert [r.memory.id for r in results] == ["mem_a"]
    assert store._collection.updated == []
    assert results[0].memory.access_log == []


# ---------------------------------------------------------------------------
# S3: presentation
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_reread_suppression(monkeypatch: pytest.MonkeyPatch) -> None:
    import ego_mcp._server_surface_memory as mem_mod

    monkeypatch.setattr(mem_mod, "_last_reread_presented_id", None)


def _logged(*moods: str) -> list[dict[str, str]]:
    return [
        {"at": f"2026-09-{index + 1:02d}T10:00:00+09:00", "mood": mood, "phase": "morning"}
        for index, mood in enumerate(moods)
    ]


def _memory_with_log(memory_id: str, *moods: str) -> Memory:
    """A memory whose log ends with the access recall just made."""
    return Memory(
        id=memory_id,
        content=f"content of {memory_id}",
        timestamp="2026-01-01T00:00:00+09:00",
        access_log=_logged(*moods),
    )


def test_reread_line_lists_the_moods_in_order() -> None:
    from ego_mcp._server_surface_memory import _reread_line

    mem = _memory_with_log("mem_x", "anxious", "calm", "grateful", "curious")
    line = _reread_line([_result(mem)])

    assert line == "You've come back to [mem_x] before — anxious, then calm, then grateful."


def test_reread_line_excludes_the_current_access() -> None:
    """The last entry is the access just made, so it is never quoted."""
    from ego_mcp._server_surface_memory import _reread_line

    mem = _memory_with_log("mem_x", "anxious", "calm", "grateful", "furious")
    line = _reread_line([_result(mem)])

    assert line is not None
    assert "furious" not in line


def test_reread_line_needs_three_previous_accesses() -> None:
    from ego_mcp._server_surface_memory import _reread_line

    # Four entries minus the current access leaves three: presented.
    assert _reread_line([_result(_memory_with_log("mem_x", "a", "b", "c", "d"))])
    # Three entries minus the current access leaves two: not yet.
    assert _reread_line([_result(_memory_with_log("mem_x", "a", "b", "c"))]) is None


def test_reread_line_needs_two_distinct_moods() -> None:
    from ego_mcp._server_surface_memory import _reread_line

    mem = _memory_with_log("mem_x", "calm", "calm", "calm", "calm")
    assert _reread_line([_result(mem)]) is None


def test_empty_moods_do_not_count_towards_distinct() -> None:
    from ego_mcp._server_surface_memory import _reread_line

    mem = _memory_with_log("mem_x", "calm", "", "calm", "calm")
    assert _reread_line([_result(mem)]) is None


def test_reread_line_collapses_consecutive_duplicates() -> None:
    from ego_mcp._server_surface_memory import _reread_line

    mem = _memory_with_log("mem_x", "anxious", "anxious", "calm", "now")
    line = _reread_line([_result(mem)])

    assert line == "You've come back to [mem_x] before — anxious, then calm."


def test_reread_line_truncates_beyond_four_moods() -> None:
    from ego_mcp._server_surface_memory import _reread_line

    mem = _memory_with_log(
        "mem_x", "anxious", "calm", "grateful", "lonely", "hopeful", "now"
    )
    line = _reread_line([_result(mem)])

    assert line == (
        "You've come back to [mem_x] before — "
        "anxious, then calm, then grateful, then others."
    )


def test_reread_line_keeps_exactly_four_moods() -> None:
    from ego_mcp._server_surface_memory import _reread_line

    mem = _memory_with_log("mem_x", "anxious", "calm", "grateful", "lonely", "now")
    line = _reread_line([_result(mem)])

    assert line == (
        "You've come back to [mem_x] before — "
        "anxious, then calm, then grateful, then lonely."
    )


def test_reread_line_ignores_proust_results() -> None:
    from ego_mcp._server_surface_memory import _reread_line

    result = _result(_memory_with_log("mem_p", "anxious", "calm", "grateful", "now"))
    result.is_proust = True
    assert _reread_line([result]) is None


def test_reread_line_prefers_more_distinct_moods_then_more_accesses() -> None:
    from ego_mcp._server_surface_memory import _reread_line

    two_moods = _result(
        _memory_with_log("mem_two", "a", "a", "b", "b", "b", "b", "now")
    )
    three_moods = _result(_memory_with_log("mem_three", "a", "b", "c", "now"))
    line = _reread_line([two_moods, three_moods])
    assert line is not None and "[mem_three]" in line


def test_reread_line_tie_breaks_on_access_count() -> None:
    from ego_mcp._server_surface_memory import _reread_line

    fewer = _result(_memory_with_log("mem_few", "a", "b", "c", "now"))
    more = _result(_memory_with_log("mem_many", "a", "b", "c", "a", "b", "now"))
    line = _reread_line([fewer, more])
    assert line is not None and "[mem_many]" in line


def test_reread_line_suppressed_on_consecutive_recall_of_same_memory() -> None:
    from ego_mcp._server_surface_memory import _reread_line

    mem = _memory_with_log("mem_x", "anxious", "calm", "grateful", "now")
    assert _reread_line([_result(mem)]) is not None
    assert _reread_line([_result(mem)]) is None


def test_reread_line_returns_after_a_different_memory_intervenes() -> None:
    from ego_mcp._server_surface_memory import _reread_line

    first = _memory_with_log("mem_x", "anxious", "calm", "grateful", "now")
    second = _memory_with_log("mem_y", "lonely", "hopeful", "warm", "now")

    assert _reread_line([_result(first)]) is not None
    assert _reread_line([_result(second)]) is not None
    assert _reread_line([_result(first)]) is not None


def test_reread_line_suppression_lasts_exactly_one_recall() -> None:
    """The rule is "not twice in a row" — the third recall may show it again."""
    from ego_mcp._server_surface_memory import _reread_line

    mem = _memory_with_log("mem_x", "anxious", "calm", "grateful", "now")
    assert _reread_line([_result(mem)]) is not None
    assert _reread_line([_result(mem)]) is None
    assert _reread_line([_result(mem)]) is not None


def test_reread_line_returns_after_a_recall_with_no_candidate() -> None:
    """A recall that presents nothing still clears the suppression marker."""
    from ego_mcp._server_surface_memory import _reread_line

    mem = _memory_with_log("mem_x", "anxious", "calm", "grateful", "now")
    plain = _memory_with_log("mem_plain", "calm", "calm", "calm", "now")

    assert _reread_line([_result(mem)]) is not None
    assert _reread_line([_result(plain)]) is None
    assert _reread_line([_result(mem)]) is not None


def test_reread_line_returns_after_an_empty_recall() -> None:
    from ego_mcp._server_surface_memory import _reread_line

    mem = _memory_with_log("mem_x", "anxious", "calm", "grateful", "now")

    assert _reread_line([_result(mem)]) is not None
    assert _reread_line([]) is None
    assert _reread_line([_result(mem)]) is not None


def test_reread_line_emits_telemetry() -> None:
    from ego_mcp._server_runtime import get_tool_metadata
    from ego_mcp._server_surface_memory import _reread_line

    mem = _memory_with_log("mem_x", "anxious", "calm", "grateful", "now")
    assert _reread_line([_result(mem)]) is not None

    meta = get_tool_metadata()
    assert meta.get("reread_presented") == "mem_x"
    assert meta.get("reread_distinct_moods") == 3


# ---------------------------------------------------------------------------
# S3: handler wiring
# ---------------------------------------------------------------------------


class _HandlerNotionStore:
    def __init__(self, notions: list[Notion] | None = None) -> None:
        self._notions = notions or []

    def search_related(self, **kwargs: Any) -> list[Notion]:
        return self._notions

    def get_associated(self, *args: Any, **kwargs: Any) -> list[Notion]:
        return []


class _HandlerMemoryStore:
    def __init__(self, results: list[MemorySearchResult], latest_emotion: str) -> None:
        self._results = results
        self._latest_emotion = latest_emotion
        self.recall_kwargs: dict[str, Any] = {}
        self._last_recall_metadata: dict[str, Any] = {"involuntary_person_ids": []}

    def collection_count(self) -> int:
        return len(self._results)

    def latest_emotion(self) -> str:
        return self._latest_emotion

    async def list_recent(self, n: int = 10) -> list[Memory]:
        raise AssertionError(
            "recall must not list the collection to learn the current mood"
        )

    async def recall(self, context: str, **kwargs: Any) -> list[MemorySearchResult]:
        self.recall_kwargs = kwargs
        return self._results


@pytest.mark.asyncio
async def test_handler_passes_latest_emotion_as_access_mood(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ego_mcp._server_surface_memory as mem_mod

    store = _HandlerMemoryStore([_result(Memory(id="mem_a", content="x"))], "melancholy")
    monkeypatch.setattr(mem_mod, "get_notion_store", lambda: _HandlerNotionStore())
    monkeypatch.setattr(mem_mod, "_collect_resonant_persons", lambda *a, **k: [])

    await mem_mod._handle_recall(
        cast(Any, SimpleNamespace()), cast(Any, store), {"context": "x"}
    )

    assert store.recall_kwargs["access_mood"] == "melancholy"


@pytest.mark.asyncio
async def test_handler_access_mood_is_empty_without_memories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing saved in this process yet: the mood stays unknown, no scan."""
    import ego_mcp._server_surface_memory as mem_mod

    store = _HandlerMemoryStore([_result(Memory(id="mem_a", content="x"))], "")
    monkeypatch.setattr(mem_mod, "get_notion_store", lambda: _HandlerNotionStore())
    monkeypatch.setattr(mem_mod, "_collect_resonant_persons", lambda *a, **k: [])

    await mem_mod._handle_recall(
        cast(Any, SimpleNamespace()), cast(Any, store), {"context": "x"}
    )

    assert store.recall_kwargs["access_mood"] == ""


@pytest.mark.asyncio
async def test_handler_access_mood_survives_a_failing_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broken mood lookup must not cost the recall itself."""
    import ego_mcp._server_surface_memory as mem_mod

    store = _HandlerMemoryStore([_result(Memory(id="mem_a", content="x"))], "calm")

    def _boom() -> str:
        raise RuntimeError("collection unavailable")

    monkeypatch.setattr(store, "latest_emotion", _boom)
    monkeypatch.setattr(mem_mod, "get_notion_store", lambda: _HandlerNotionStore())
    monkeypatch.setattr(mem_mod, "_collect_resonant_persons", lambda *a, **k: [])

    text = await mem_mod._handle_recall(
        cast(Any, SimpleNamespace()), cast(Any, store), {"context": "x"}
    )

    assert store.recall_kwargs["access_mood"] == ""
    assert "1 of ~1 memories" in text


@pytest.mark.asyncio
async def test_handler_places_reread_line_after_notions_before_people(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ego_mcp._server_surface_memory as mem_mod

    mem = _memory_with_log("mem_x", "anxious", "calm", "grateful", "now")
    mem.tags = ["home"]
    store = _HandlerMemoryStore([_result(mem)], "calm")
    notion = Notion(
        id="notion_1",
        label="home & safety",
        emotion_tone=Emotion.ANXIOUS,
        confidence=0.9,
        tags=["home"],
    )
    monkeypatch.setattr(
        mem_mod, "get_notion_store", lambda: _HandlerNotionStore([notion])
    )
    monkeypatch.setattr(
        mem_mod,
        "_collect_resonant_persons",
        lambda *a, **k: [
            type("RP", (), {"person_id": "alice", "name": "Alice"})(),
        ],
    )

    text = await mem_mod._handle_recall(
        cast(Any, SimpleNamespace()), cast(Any, store), {"context": "x"}
    )

    reread = "You've come back to [mem_x] before — anxious, then calm, then grateful."
    assert reread in text
    assert text.index("--- notions ---") < text.index(reread)
    assert text.index(reread) < text.index("Alice")


@pytest.mark.asyncio
async def test_handler_omits_reread_line_when_unqualified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ego_mcp._server_surface_memory as mem_mod

    mem = _memory_with_log("mem_x", "calm", "calm", "calm", "calm")
    store = _HandlerMemoryStore([_result(mem)], "calm")
    monkeypatch.setattr(mem_mod, "get_notion_store", lambda: _HandlerNotionStore())
    monkeypatch.setattr(mem_mod, "_collect_resonant_persons", lambda *a, **k: [])

    text = await mem_mod._handle_recall(
        cast(Any, SimpleNamespace()), cast(Any, store), {"context": "x"}
    )

    assert "You've come back to" not in text


@pytest.mark.asyncio
async def test_handler_does_not_alter_the_memory_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T9: re-reading records the return, never rewrites what was written."""
    import ego_mcp._server_surface_memory as mem_mod

    mem = _memory_with_log("mem_x", "anxious", "calm", "grateful", "now")
    mem.content = "I was afraid the whole way home."
    store = _HandlerMemoryStore([_result(mem)], "calm")
    monkeypatch.setattr(mem_mod, "get_notion_store", lambda: _HandlerNotionStore())
    monkeypatch.setattr(mem_mod, "_collect_resonant_persons", lambda *a, **k: [])

    text = await mem_mod._handle_recall(
        cast(Any, SimpleNamespace()), cast(Any, store), {"context": "x"}
    )

    assert "I was afraid the whole way home." in text


@pytest.mark.asyncio
async def test_handler_empty_recall_clears_the_suppression_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A recall that returns nothing at all still counts as "not in a row"."""
    import ego_mcp._server_surface_memory as mem_mod

    mem = _memory_with_log("mem_x", "anxious", "calm", "grateful", "now")
    assert mem_mod._reread_line([_result(mem)]) is not None

    empty_store = _HandlerMemoryStore([], "calm")
    monkeypatch.setattr(mem_mod, "get_notion_store", lambda: _HandlerNotionStore())
    monkeypatch.setattr(mem_mod, "_collect_resonant_persons", lambda *a, **k: [])

    text = await mem_mod._handle_recall(
        cast(Any, SimpleNamespace()), cast(Any, empty_store), {"context": "x"}
    )

    assert "No related memories found." in text
    assert mem_mod._last_reread_presented_id is None
    assert mem_mod._reread_line([_result(mem)]) is not None


@pytest.mark.asyncio
async def test_handler_unqualified_recall_clears_the_suppression_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An intervening recall without a qualifying memory must not keep the
    previous one suppressed until the process restarts."""
    import ego_mcp._server_surface_memory as mem_mod

    mem = _memory_with_log("mem_x", "anxious", "calm", "grateful", "now")
    plain = _memory_with_log("mem_plain", "calm", "calm", "calm", "now")
    monkeypatch.setattr(mem_mod, "get_notion_store", lambda: _HandlerNotionStore())
    monkeypatch.setattr(mem_mod, "_collect_resonant_persons", lambda *a, **k: [])

    reread = "You've come back to [mem_x] before"

    first = await mem_mod._handle_recall(
        cast(Any, SimpleNamespace()),
        cast(Any, _HandlerMemoryStore([_result(mem)], "calm")),
        {"context": "x"},
    )
    assert reread in first

    middle = await mem_mod._handle_recall(
        cast(Any, SimpleNamespace()),
        cast(Any, _HandlerMemoryStore([_result(plain)], "calm")),
        {"context": "x"},
    )
    assert "You've come back to" not in middle

    third = await mem_mod._handle_recall(
        cast(Any, SimpleNamespace()),
        cast(Any, _HandlerMemoryStore([_result(mem)], "calm")),
        {"context": "x"},
    )
    assert reread in third


# ---------------------------------------------------------------------------
# S3: the cached current mood (MemoryStore.latest_emotion)
# ---------------------------------------------------------------------------


class _FakeEmbeddingProvider:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]


@pytest.fixture
def mood_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[MemoryStore]:
    from ego_mcp.embedding import EgoEmbeddingFunction, EmbeddingProvider

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("EGO_MCP_DATA_DIR", str(tmp_path / "ego-data"))
    provider: EmbeddingProvider = _FakeEmbeddingProvider()
    store = MemoryStore(EgoConfig.from_env(), EgoEmbeddingFunction(provider))
    store.connect()
    yield store
    store.close()


def test_latest_emotion_is_empty_before_anything_is_saved(
    mood_store: MemoryStore,
) -> None:
    """No startup scan: an unknown mood is allowed and costs nothing."""
    assert mood_store.latest_emotion() == ""


@pytest.mark.asyncio
async def test_save_updates_the_cached_latest_emotion(
    mood_store: MemoryStore,
) -> None:
    await mood_store.save("first", emotion="anxious")
    assert mood_store.latest_emotion() == "anxious"

    await mood_store.save("second", emotion="grateful")
    assert mood_store.latest_emotion() == "grateful"


@pytest.mark.asyncio
async def test_save_with_auto_link_updates_the_cached_latest_emotion(
    mood_store: MemoryStore,
) -> None:
    await mood_store.save_with_auto_link("a walk in the rain", emotion="melancholy")
    assert mood_store.latest_emotion() == "melancholy"


@pytest.mark.asyncio
async def test_an_older_memory_does_not_overwrite_the_cached_emotion(
    mood_store: MemoryStore,
) -> None:
    await mood_store.save("newest", emotion="grateful")

    older = Memory(
        id="mem_old",
        content="written long ago",
        timestamp="2000-01-01T00:00:00+09:00",
        emotional_trace=EmotionalTrace(primary=Emotion.ANXIOUS),
    )
    mood_store._remember_latest_emotion(older)

    assert mood_store.latest_emotion() == "grateful"


@pytest.mark.asyncio
async def test_a_memory_with_the_same_timestamp_overwrites_the_cached_emotion(
    mood_store: MemoryStore,
) -> None:
    saved = await mood_store.save("newest", emotion="grateful")

    same_moment = Memory(
        id="mem_tie",
        content="the same instant",
        timestamp=saved.timestamp,
        emotional_trace=EmotionalTrace(primary=Emotion.ANXIOUS),
    )
    mood_store._remember_latest_emotion(same_moment)

    assert mood_store.latest_emotion() == "anxious"


def test_unparsable_timestamps_never_raise() -> None:
    from ego_mcp._memory_store import _timestamp_at_least

    assert _timestamp_at_least("not a date", "") is True
    assert _timestamp_at_least("", "2026-09-17T00:00:00+09:00") is False
