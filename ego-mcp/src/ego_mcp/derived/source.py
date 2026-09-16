"""Read-only snapshot of everything a derived lens may look at (D0 S4).

Nothing in this module writes to the primary stores. ChromaDB is opened
directly (no ``MemoryStore``, which self-heals its FTS index on connect) and
the JSON stores are parsed with plain :mod:`json` (no ``SelfModelStore``, whose
constructor can rescue orphans by writing).
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from ego_mcp import timezone_utils
from ego_mcp._memory_serialization import memory_from_chromadb
from ego_mcp.chromadb_compat import load_chromadb
from ego_mcp.derived.co_retrieval_log import read_co_retrieval
from ego_mcp.derived.contract import DerivedReader
from ego_mcp.notion import NotionStore
from ego_mcp.self_model import normalize_question_log
from ego_mcp.types import Memory, Notion

logger = logging.getLogger(__name__)

DERIVED_MAX_MEMORIES = 20_000
DERIVED_CHROMA_PAGE = 2_000
MEMORY_COLLECTION_NAME = "ego_memories"

#: One retry, after this many seconds, when chromadb raises mid-read (the
#: server may be flushing an HNSW segment).
CHROMA_RETRY_DELAY_SECONDS = 5.0

#: Exception classes chromadb uses for "this collection was never created".
#: 1.x raises ``chromadb.errors.NotFoundError``; 0.5.x raised
#: ``chromadb.errors.InvalidCollectionException``. Looked up by name so a
#: version that ships only one of them still works.
_MISSING_COLLECTION_ERROR_NAMES = (
    "NotFoundError",
    "InvalidCollectionException",
    "CollectionNotDefinedError",
)

#: Older chromadb signalled the same thing with a plain ``ValueError`` whose
#: message names the collection. Matched on the message only for those two
#: builtin types — never for an arbitrary exception.
_MISSING_COLLECTION_MESSAGES = ("does not exist", "not found", "no such collection")


class SnapshotUnavailable(RuntimeError):
    """Raised when the memory store could not be read even after a retry."""


@dataclass(frozen=True)
class SourceSnapshot:
    """Everything a lens is allowed to see, frozen at one moment."""

    now: datetime
    memories: list[Memory]
    embeddings: dict[str, np.ndarray] | None
    notions: list[Notion]
    question_log: list[dict[str, Any]]
    relationships: dict[str, dict[str, Any]]
    surfaced: dict[str, str]
    co_retrievals: list[tuple[datetime, list[str]]]

    @property
    def memory_count(self) -> int:
        return len(self.memories)

    @property
    def embedding_count(self) -> int:
        return 0 if self.embeddings is None else len(self.embeddings)

    def source_stats(self) -> dict[str, int]:
        """The ``source`` block written into every lens file."""
        return {
            "memory_count": self.memory_count,
            "notion_count": len(self.notions),
            "embedding_count": self.embedding_count,
        }


def load_snapshot(
    data_dir: Path,
    *,
    with_embeddings: bool,
    now: datetime | None = None,
) -> SourceSnapshot:
    """Load a read-only snapshot of the memory store and JSON stores.

    Raises:
        SnapshotUnavailable: if ChromaDB could not be read twice in a row.
    """
    moment = now if now is not None else timezone_utils.now()

    memories, raw_embeddings = _load_memories(data_dir, with_embeddings=with_embeddings)
    memories.sort(key=lambda memory: memory.timestamp, reverse=True)

    embeddings: dict[str, np.ndarray] | None = None
    if with_embeddings:
        allowed_ids = {memory.id for memory in memories[:DERIVED_MAX_MEMORIES]}
        embeddings = _normalize_embeddings(raw_embeddings, allowed_ids)

    return SourceSnapshot(
        now=moment,
        memories=memories,
        embeddings=embeddings,
        notions=_load_notions(data_dir),
        question_log=_load_question_log(data_dir),
        relationships=_load_relationships(data_dir),
        surfaced=DerivedReader(data_dir).marks(),
        co_retrievals=read_co_retrieval(data_dir),
    )


# --- ChromaDB ---------------------------------------------------------------


def _is_missing_collection(chromadb: Any, exc: BaseException) -> bool:
    """Return whether ``exc`` means the collection was never created.

    Anything else — a locked database, a corrupt segment, a fallback module
    without ``get_collection`` — is a failure to read, not an absence, and must
    not be flattened into an empty snapshot.
    """
    errors = getattr(chromadb, "errors", None)
    for name in _MISSING_COLLECTION_ERROR_NAMES:
        error_type = getattr(errors, name, None)
        if (
            isinstance(error_type, type)
            and issubclass(error_type, BaseException)
            and isinstance(exc, error_type)
        ):
            return True
    if isinstance(exc, (ValueError, KeyError)):
        message = str(exc).lower()
        return any(fragment in message for fragment in _MISSING_COLLECTION_MESSAGES)
    return False


def _open_collection(data_dir: Path) -> Any | None:
    """Open the memory collection read-only, or return ``None`` if absent.

    Only a genuine "no such collection" reads as ``None``; every other error
    propagates into the retry in :func:`_load_memories` and, if it survives
    that, into :class:`SnapshotUnavailable`.
    """
    chromadb = load_chromadb()
    client = chromadb.PersistentClient(path=str(data_dir / "chroma"))
    try:
        return client.get_collection(name=MEMORY_COLLECTION_NAME)
    except Exception as exc:
        if _is_missing_collection(chromadb, exc):
            logger.debug("Memory collection has not been created yet: %s", exc)
            return None
        raise


def _load_memories(
    data_dir: Path, *, with_embeddings: bool
) -> tuple[list[Memory], dict[str, Any]]:
    """Page the whole collection, retrying once on a concurrent-write error."""
    try:
        return _read_collection(data_dir, with_embeddings=with_embeddings)
    except Exception as first_error:
        logger.debug("Snapshot read failed, retrying once: %s", first_error)
        time.sleep(CHROMA_RETRY_DELAY_SECONDS)
        try:
            return _read_collection(data_dir, with_embeddings=with_embeddings)
        except Exception as second_error:
            raise SnapshotUnavailable(
                f"Could not read the memory store at {data_dir}: {second_error}"
            ) from second_error


def _read_collection(
    data_dir: Path, *, with_embeddings: bool
) -> tuple[list[Memory], dict[str, Any]]:
    collection = _open_collection(data_dir)
    if collection is None:
        return [], {}

    include = ["documents", "metadatas"]
    if with_embeddings:
        include = include + ["embeddings"]

    memories: list[Memory] = []
    vectors: dict[str, Any] = {}
    offset = 0
    while True:
        page = collection.get(
            limit=DERIVED_CHROMA_PAGE,
            offset=offset,
            include=include,
        )
        ids = list(page.get("ids") or [])
        if not ids:
            break
        documents = _sequence_or_blanks(page.get("documents"), len(ids), "")
        metadatas = _sequence_or_blanks(page.get("metadatas"), len(ids), None)
        embeddings_page = page.get("embeddings")
        for index, memory_id in enumerate(ids):
            metadata = metadatas[index]
            memories.append(
                memory_from_chromadb(
                    memory_id,
                    documents[index] or "",
                    metadata if isinstance(metadata, dict) else {},
                )
            )
            if with_embeddings and embeddings_page is not None:
                try:
                    vectors[memory_id] = embeddings_page[index]
                except (IndexError, KeyError, TypeError):
                    continue
        if len(ids) < DERIVED_CHROMA_PAGE:
            break
        offset += len(ids)
    return memories, vectors


def _sequence_or_blanks(value: Any, length: int, blank: Any) -> list[Any]:
    """Return ``value`` as a list of ``length`` entries, padding with ``blank``."""
    if value is None:
        return [blank] * length
    items = list(value)
    if len(items) < length:
        items.extend([blank] * (length - len(items)))
    return items


def _normalize_embeddings(
    raw: dict[str, Any], allowed_ids: set[str]
) -> dict[str, np.ndarray]:
    """L2-normalize vectors, keeping only the majority dimension.

    A provider change leaves vectors of two different widths in the collection;
    anything that is not the majority width is dropped rather than crashing a
    lens with a shape error.
    """
    candidates: dict[str, np.ndarray] = {}
    for memory_id, vector in raw.items():
        if memory_id not in allowed_ids or vector is None:
            continue
        try:
            array = np.asarray(vector, dtype=np.float32)
        except (TypeError, ValueError):
            continue
        if array.ndim != 1 or array.size == 0:
            continue
        candidates[memory_id] = array

    if not candidates:
        return {}

    widths = Counter(array.shape[0] for array in candidates.values())
    majority_width = widths.most_common(1)[0][0]

    normalized: dict[str, np.ndarray] = {}
    for memory_id, array in candidates.items():
        if array.shape[0] != majority_width:
            continue
        norm = float(np.linalg.norm(array))
        if norm < 1e-8:
            continue
        normalized[memory_id] = (array / norm).astype(np.float32)
    return normalized


# --- JSON stores ------------------------------------------------------------


def _read_json(path: Path) -> Any:
    """Read a JSON file; a missing or corrupt file reads as ``None``."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.debug("Derived snapshot: %s is not valid JSON", path)
        return None


def _load_notions(data_dir: Path) -> list[Notion]:
    payload = _read_json(data_dir / "notions.json")
    if not isinstance(payload, dict):
        return []
    notions: list[Notion] = []
    for entry in payload.values():
        if not isinstance(entry, dict):
            continue
        try:
            notions.append(NotionStore._from_payload(entry))
        except (TypeError, ValueError):
            continue
    notions.sort(key=lambda notion: notion.created, reverse=True)
    return notions


def _load_question_log(data_dir: Path) -> list[dict[str, Any]]:
    payload = _read_json(data_dir / "self_model.json")
    if not isinstance(payload, dict):
        return []
    return normalize_question_log(payload.get("question_log", []))


def _load_relationships(data_dir: Path) -> dict[str, dict[str, Any]]:
    payload = _read_json(data_dir / "relationships" / "models.json")
    if not isinstance(payload, dict):
        return {}
    return {
        str(person_id): model
        for person_id, model in payload.items()
        if isinstance(model, dict)
    }
