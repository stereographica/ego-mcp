"""Tests for derived/source.py and derived/co_retrieval_log.py (D0 S4 / P1 S1)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from ego_mcp.derived import co_retrieval_log, source
from ego_mcp.derived.co_retrieval_log import (
    CO_RETRIEVAL_LOG_MAX,
    append_co_retrieval,
    co_retrieval_path,
    read_co_retrieval,
)
from ego_mcp.derived.source import SnapshotUnavailable, load_snapshot

TZ = timezone(timedelta(hours=9))
NOW = datetime(2026, 9, 16, 3, 0, 0, tzinfo=TZ)


# --- fake chromadb ----------------------------------------------------------


class FakeCollection:
    """Minimal stand-in for a chromadb collection supporting paged ``get``."""

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records
        self.get_calls: list[tuple[int, int, tuple[str, ...]]] = []

    def count(self) -> int:
        return len(self._records)

    def get(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        include = include or []
        self.get_calls.append((limit or 0, offset, tuple(include)))
        page = self._records[offset : offset + (limit or len(self._records))]
        result: dict[str, Any] = {"ids": [r["id"] for r in page]}
        if "documents" in include:
            result["documents"] = [r["document"] for r in page]
        if "metadatas" in include:
            result["metadatas"] = [r["metadata"] for r in page]
        if "embeddings" in include:
            result["embeddings"] = [r.get("embedding") for r in page]
        return result


class FakeClient:
    def __init__(self, collection: FakeCollection | None) -> None:
        self._collection = collection

    def get_collection(self, name: str) -> FakeCollection:
        if self._collection is None:
            raise ValueError(f"Collection {name} does not exist.")
        return self._collection


class FakeChromadb:
    def __init__(self, collection: FakeCollection | None) -> None:
        self._collection = collection
        self.paths: list[str] = []

    def PersistentClient(self, path: str) -> FakeClient:  # noqa: N802 (chromadb API)
        self.paths.append(path)
        return FakeClient(self._collection)


def _record(
    memory_id: str,
    *,
    timestamp: datetime,
    embedding: list[float] | None = None,
    linked: list[str] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "emotion": "joy",
        "intensity": 0.7,
        "importance": 4,
        "category": "daily",
        "timestamp": timestamp.isoformat(),
        "valence": 0.4,
        "arousal": 0.5,
        "tags": "a,b",
        "is_private": False,
        "access_count": 1,
    }
    if linked:
        metadata["linked_ids"] = json.dumps(
            [
                {"target_id": target, "link_type": "related", "confidence": 0.5}
                for target in linked
            ]
        )
    record: dict[str, Any] = {
        "id": memory_id,
        "document": f"content of {memory_id}",
        "metadata": metadata,
    }
    if embedding is not None:
        record["embedding"] = embedding
    return record


@pytest.fixture
def install_chromadb(monkeypatch: pytest.MonkeyPatch) -> Any:
    def _install(collection: FakeCollection | None) -> FakeChromadb:
        fake = FakeChromadb(collection)
        monkeypatch.setattr(source, "load_chromadb", lambda: fake)
        return fake

    return _install


# --- basic loading ----------------------------------------------------------


def test_load_snapshot_sorts_memories_newest_first(
    tmp_path: Path, install_chromadb: Any
) -> None:
    collection = FakeCollection(
        [
            _record("m_old", timestamp=NOW - timedelta(days=5)),
            _record("m_new", timestamp=NOW),
            _record("m_mid", timestamp=NOW - timedelta(days=1)),
        ]
    )
    install_chromadb(collection)

    snapshot = load_snapshot(tmp_path, with_embeddings=False, now=NOW)
    assert [m.id for m in snapshot.memories] == ["m_new", "m_mid", "m_old"]
    assert snapshot.embeddings is None
    assert snapshot.now == NOW
    assert snapshot.source_stats() == {
        "memory_count": 3,
        "notion_count": 0,
        "embedding_count": 0,
    }


def test_load_snapshot_opens_the_chroma_subdirectory(
    tmp_path: Path, install_chromadb: Any
) -> None:
    fake = install_chromadb(FakeCollection([]))
    load_snapshot(tmp_path, with_embeddings=False, now=NOW)
    assert fake.paths == [str(tmp_path / "chroma")]


def test_load_snapshot_missing_collection_is_empty(
    tmp_path: Path, install_chromadb: Any
) -> None:
    install_chromadb(None)
    snapshot = load_snapshot(tmp_path, with_embeddings=True, now=NOW)
    assert snapshot.memories == []
    assert snapshot.embeddings == {}


def test_load_snapshot_restores_links(tmp_path: Path, install_chromadb: Any) -> None:
    install_chromadb(
        FakeCollection(
            [
                _record("a", timestamp=NOW, linked=["b"]),
                _record("b", timestamp=NOW - timedelta(days=1)),
            ]
        )
    )
    snapshot = load_snapshot(tmp_path, with_embeddings=False, now=NOW)
    assert snapshot.memories[0].linked_ids[0].target_id == "b"


def test_load_snapshot_defaults_now_to_app_timezone(
    tmp_path: Path, install_chromadb: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_chromadb(FakeCollection([]))
    monkeypatch.setenv("EGO_MCP_TIMEZONE", "Asia/Tokyo")
    snapshot = load_snapshot(tmp_path, with_embeddings=False)
    assert snapshot.now.tzinfo is not None


# --- paging -----------------------------------------------------------------


def test_load_snapshot_pages_past_the_page_size(
    tmp_path: Path, install_chromadb: Any
) -> None:
    total = source.DERIVED_CHROMA_PAGE * 2 + 37
    records = [
        _record(f"m{i:05d}", timestamp=NOW - timedelta(minutes=i)) for i in range(total)
    ]
    collection = FakeCollection(records)
    install_chromadb(collection)

    snapshot = load_snapshot(tmp_path, with_embeddings=False, now=NOW)
    assert len(snapshot.memories) == total
    assert len({m.id for m in snapshot.memories}) == total

    offsets = [call[1] for call in collection.get_calls]
    limits = {call[0] for call in collection.get_calls}
    assert limits == {source.DERIVED_CHROMA_PAGE}
    assert offsets == [0, source.DERIVED_CHROMA_PAGE, source.DERIVED_CHROMA_PAGE * 2]


def test_load_snapshot_stops_on_exact_multiple_of_page_size(
    tmp_path: Path, install_chromadb: Any
) -> None:
    total = source.DERIVED_CHROMA_PAGE * 2
    collection = FakeCollection(
        [_record(f"m{i:05d}", timestamp=NOW - timedelta(minutes=i)) for i in range(total)]
    )
    install_chromadb(collection)
    snapshot = load_snapshot(tmp_path, with_embeddings=False, now=NOW)
    assert len(snapshot.memories) == total
    # Three calls: two full pages plus the empty page that ends the loop.
    assert len(collection.get_calls) == 3


def test_load_snapshot_requests_embeddings_only_when_asked(
    tmp_path: Path, install_chromadb: Any
) -> None:
    collection = FakeCollection([_record("a", timestamp=NOW, embedding=[1.0, 0.0])])
    install_chromadb(collection)

    load_snapshot(tmp_path, with_embeddings=False, now=NOW)
    assert collection.get_calls[0][2] == ("documents", "metadatas")

    collection.get_calls.clear()
    load_snapshot(tmp_path, with_embeddings=True, now=NOW)
    assert collection.get_calls[0][2] == ("documents", "metadatas", "embeddings")


# --- embeddings -------------------------------------------------------------


def test_embeddings_are_l2_normalized_float32(
    tmp_path: Path, install_chromadb: Any
) -> None:
    install_chromadb(
        FakeCollection([_record("a", timestamp=NOW, embedding=[3.0, 4.0])])
    )
    snapshot = load_snapshot(tmp_path, with_embeddings=True, now=NOW)
    assert snapshot.embeddings is not None
    vector = snapshot.embeddings["a"]
    assert vector.dtype == np.float32
    assert float(np.linalg.norm(vector)) == pytest.approx(1.0, abs=1e-6)
    assert vector.tolist() == pytest.approx([0.6, 0.8], abs=1e-6)


def test_embedding_cap_keeps_only_the_newest_memories(
    tmp_path: Path, install_chromadb: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(source, "DERIVED_MAX_MEMORIES", 2)
    install_chromadb(
        FakeCollection(
            [
                _record("old", timestamp=NOW - timedelta(days=9), embedding=[1.0, 0.0]),
                _record("mid", timestamp=NOW - timedelta(days=1), embedding=[0.0, 1.0]),
                _record("new", timestamp=NOW, embedding=[1.0, 1.0]),
            ]
        )
    )
    snapshot = load_snapshot(tmp_path, with_embeddings=True, now=NOW)
    assert len(snapshot.memories) == 3
    assert snapshot.embeddings is not None
    assert set(snapshot.embeddings) == {"new", "mid"}
    assert snapshot.embedding_count == 2


def test_embeddings_drop_minority_dimensions(
    tmp_path: Path, install_chromadb: Any
) -> None:
    install_chromadb(
        FakeCollection(
            [
                _record("a", timestamp=NOW, embedding=[1.0, 0.0, 0.0]),
                _record("b", timestamp=NOW - timedelta(minutes=1), embedding=[0.0, 1.0, 0.0]),
                _record("c", timestamp=NOW - timedelta(minutes=2), embedding=[1.0, 0.0]),
            ]
        )
    )
    snapshot = load_snapshot(tmp_path, with_embeddings=True, now=NOW)
    assert snapshot.embeddings is not None
    assert set(snapshot.embeddings) == {"a", "b"}


def test_embeddings_skip_missing_and_degenerate_vectors(
    tmp_path: Path, install_chromadb: Any
) -> None:
    install_chromadb(
        FakeCollection(
            [
                _record("a", timestamp=NOW, embedding=[1.0, 0.0]),
                _record("zero", timestamp=NOW - timedelta(minutes=1), embedding=[0.0, 0.0]),
                _record("none", timestamp=NOW - timedelta(minutes=2), embedding=None),
            ]
        )
    )
    snapshot = load_snapshot(tmp_path, with_embeddings=True, now=NOW)
    assert snapshot.embeddings is not None
    assert set(snapshot.embeddings) == {"a"}


# --- retry / failure --------------------------------------------------------


def test_load_snapshot_retries_once_then_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    collection = FakeCollection([_record("a", timestamp=NOW)])
    attempts = {"n": 0}

    class FlakyChromadb(FakeChromadb):
        def PersistentClient(self, path: str) -> FakeClient:  # noqa: N802
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("hnsw segment busy")
            return FakeClient(collection)

    monkeypatch.setattr(source, "load_chromadb", lambda: FlakyChromadb(collection))
    slept: list[float] = []
    monkeypatch.setattr("ego_mcp.derived.source.time.sleep", lambda seconds: slept.append(seconds))

    snapshot = load_snapshot(tmp_path, with_embeddings=False, now=NOW)
    assert [m.id for m in snapshot.memories] == ["a"]
    assert attempts["n"] == 2
    assert slept == [source.CHROMA_RETRY_DELAY_SECONDS]


def test_load_snapshot_raises_snapshot_unavailable_after_second_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrokenChromadb:
        def PersistentClient(self, path: str) -> FakeClient:  # noqa: N802
            raise RuntimeError("still busy")

    monkeypatch.setattr(source, "load_chromadb", lambda: BrokenChromadb())
    monkeypatch.setattr("ego_mcp.derived.source.time.sleep", lambda seconds: None)

    with pytest.raises(SnapshotUnavailable):
        load_snapshot(tmp_path, with_embeddings=False, now=NOW)


# --- JSON stores ------------------------------------------------------------


def _write_json_stores(data_dir: Path) -> dict[Path, tuple[bytes, float]]:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "relationships").mkdir(parents=True, exist_ok=True)

    (data_dir / "notions.json").write_text(
        json.dumps(
            {
                "notion_1": {
                    "id": "notion_1",
                    "label": "quiet mornings",
                    "emotion_tone": "joy",
                    "valence": 0.3,
                    "confidence": 0.8,
                    "source_memory_ids": ["a"],
                    "tags": ["morning"],
                    "created": "2026-09-01T00:00:00+09:00",
                },
                "broken": "not a dict",
            }
        ),
        encoding="utf-8",
    )
    (data_dir / "self_model.json").write_text(
        json.dumps(
            {
                "question_log": [
                    {"id": "q_1", "question": "what am I circling?", "importance": 9},
                    {"no_question": True},
                    "nope",
                ]
            }
        ),
        encoding="utf-8",
    )
    (data_dir / "relationships" / "models.json").write_text(
        json.dumps({"person_1": {"person_id": "person_1", "trust_level": 0.7}, "bad": 3}),
        encoding="utf-8",
    )

    return {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in (
            data_dir / "notions.json",
            data_dir / "self_model.json",
            data_dir / "relationships" / "models.json",
        )
    }


def test_load_snapshot_reads_json_stores(tmp_path: Path, install_chromadb: Any) -> None:
    install_chromadb(FakeCollection([_record("a", timestamp=NOW)]))
    _write_json_stores(tmp_path)

    snapshot = load_snapshot(tmp_path, with_embeddings=False, now=NOW)

    assert [notion.id for notion in snapshot.notions] == ["notion_1"]
    assert snapshot.notions[0].label == "quiet mornings"
    assert [entry["id"] for entry in snapshot.question_log] == ["q_1"]
    # normalize_question_log clamps importance into 1..5
    assert snapshot.question_log[0]["importance"] == 5
    assert set(snapshot.relationships) == {"person_1"}
    assert snapshot.source_stats()["notion_count"] == 1


def test_load_snapshot_does_not_mutate_json_stores(
    tmp_path: Path, install_chromadb: Any
) -> None:
    install_chromadb(FakeCollection([_record("a", timestamp=NOW)]))
    before = _write_json_stores(tmp_path)

    load_snapshot(tmp_path, with_embeddings=False, now=NOW)

    for path, (content, mtime) in before.items():
        assert path.read_bytes() == content
        assert path.stat().st_mtime_ns == mtime


def test_load_snapshot_does_not_create_json_stores(
    tmp_path: Path, install_chromadb: Any
) -> None:
    install_chromadb(FakeCollection([]))
    load_snapshot(tmp_path, with_embeddings=False, now=NOW)
    assert not (tmp_path / "self_model.json").exists()
    assert not (tmp_path / "notions.json").exists()
    assert not (tmp_path / "relationships").exists()


def test_load_snapshot_treats_corrupt_json_stores_as_empty(
    tmp_path: Path, install_chromadb: Any
) -> None:
    install_chromadb(FakeCollection([]))
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "relationships").mkdir(parents=True, exist_ok=True)
    (tmp_path / "notions.json").write_text("{oops", encoding="utf-8")
    (tmp_path / "self_model.json").write_text("[]", encoding="utf-8")
    (tmp_path / "relationships" / "models.json").write_text("null", encoding="utf-8")

    snapshot = load_snapshot(tmp_path, with_embeddings=False, now=NOW)
    assert snapshot.notions == []
    assert snapshot.question_log == []
    assert snapshot.relationships == {}


def test_load_snapshot_reads_surfaced_marks(
    tmp_path: Path, install_chromadb: Any
) -> None:
    install_chromadb(FakeCollection([]))
    derived = tmp_path / "derived"
    derived.mkdir(parents=True)
    (derived / "surfaced.json").write_text(
        json.dumps({"schema": 1, "marks": {"recurrence:a:2026-09-16": NOW.isoformat()}}),
        encoding="utf-8",
    )
    snapshot = load_snapshot(tmp_path, with_embeddings=False, now=NOW)
    assert snapshot.surfaced == {"recurrence:a:2026-09-16": NOW.isoformat()}


# --- co-retrieval log -------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_co_retrieval_counter() -> Any:
    co_retrieval_log._reset_counter_for_tests()
    yield
    co_retrieval_log._reset_counter_for_tests()


def test_append_co_retrieval_writes_one_line(tmp_path: Path) -> None:
    append_co_retrieval(tmp_path, ["mem_a", "mem_b"], now=NOW)
    lines = co_retrieval_path(tmp_path).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {"at": NOW.isoformat(), "ids": ["mem_a", "mem_b"]}


def test_append_co_retrieval_skips_fewer_than_two_ids(tmp_path: Path) -> None:
    append_co_retrieval(tmp_path, [], now=NOW)
    append_co_retrieval(tmp_path, ["mem_a"], now=NOW)
    append_co_retrieval(tmp_path, ["mem_a", ""], now=NOW)
    assert not co_retrieval_path(tmp_path).exists()


def test_append_co_retrieval_never_raises(tmp_path: Path) -> None:
    # derived/ occupied by a file: mkdir fails, and the append must stay silent.
    (tmp_path / "derived").write_text("blocked", encoding="utf-8")
    append_co_retrieval(tmp_path, ["mem_a", "mem_b"], now=NOW)


def test_append_co_retrieval_trims_to_the_cap_on_the_counted_append(
    tmp_path: Path,
) -> None:
    path = co_retrieval_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    surplus = 40
    with path.open("w", encoding="utf-8") as handle:
        for i in range(CO_RETRIEVAL_LOG_MAX + surplus):
            handle.write(json.dumps({"at": NOW.isoformat(), "ids": [f"x{i}", "y"]}) + "\n")

    for _ in range(co_retrieval_log._LINE_CHECK_INTERVAL):
        append_co_retrieval(tmp_path, ["mem_a", "mem_b"], now=NOW)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == CO_RETRIEVAL_LOG_MAX
    assert json.loads(lines[-1])["ids"] == ["mem_a", "mem_b"]
    # The oldest lines were the ones dropped.
    assert json.loads(lines[0])["ids"][0].startswith("x")
    assert int(json.loads(lines[0])["ids"][0][1:]) == surplus + co_retrieval_log._LINE_CHECK_INTERVAL


def test_append_co_retrieval_does_not_count_every_call(tmp_path: Path) -> None:
    path = co_retrieval_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for i in range(CO_RETRIEVAL_LOG_MAX + 10):
            handle.write(json.dumps({"at": NOW.isoformat(), "ids": [f"x{i}", "y"]}) + "\n")

    append_co_retrieval(tmp_path, ["mem_a", "mem_b"], now=NOW)
    assert len(path.read_text(encoding="utf-8").splitlines()) == CO_RETRIEVAL_LOG_MAX + 11


def test_read_co_retrieval_skips_unparsable_lines(tmp_path: Path) -> None:
    path = co_retrieval_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                json.dumps({"at": NOW.isoformat(), "ids": ["a", "b"]}),
                "{broken",
                "",
                json.dumps(["not", "an", "object"]),
                json.dumps({"ids": ["a", "b"]}),
                json.dumps({"at": "not-a-date", "ids": ["a", "b"]}),
                json.dumps({"at": NOW.isoformat(), "ids": "abc"}),
                json.dumps({"at": NOW.isoformat(), "ids": [1, 2]}),
                json.dumps({"at": (NOW + timedelta(days=1)).isoformat(), "ids": ["c", "d", 5]}),
            ]
        ),
        encoding="utf-8",
    )
    entries = read_co_retrieval(tmp_path)
    assert entries == [
        (NOW, ["a", "b"]),
        (NOW + timedelta(days=1), ["c", "d"]),
    ]


def test_read_co_retrieval_missing_file(tmp_path: Path) -> None:
    assert read_co_retrieval(tmp_path) == []


def test_snapshot_carries_co_retrievals(tmp_path: Path, install_chromadb: Any) -> None:
    install_chromadb(FakeCollection([]))
    append_co_retrieval(tmp_path, ["mem_a", "mem_b"], now=NOW)
    snapshot = load_snapshot(tmp_path, with_embeddings=False, now=NOW)
    assert snapshot.co_retrievals == [(NOW, ["mem_a", "mem_b"])]
