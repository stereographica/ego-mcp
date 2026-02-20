"""Minimal local fallback for a subset of ChromaDB APIs used by ego-mcp."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


def _cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 1.0
    return 1.0 - (dot / (na * nb))


def _match_where(metadata: dict[str, Any], where: dict[str, Any] | None) -> bool:
    if where is None:
        return True
    if "$and" in where:
        clauses = where.get("$and")
        if not isinstance(clauses, list):
            return False
        return all(_match_where(metadata, c) for c in clauses if isinstance(c, dict))
    for k, v in where.items():
        if metadata.get(k) != v:
            return False
    return True


@dataclass
class _Record:
    document: str
    metadata: dict[str, Any]
    embedding: list[float]


class Collection:
    """In-memory collection with a Chroma-like interface."""

    def __init__(self, embedding_function: Any) -> None:
        self._embedding_function = embedding_function
        self._records: dict[str, _Record] = {}

    def add(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
        embeddings: list[list[float]] | None = None,
    ) -> None:
        metas = metadatas or [{} for _ in documents]
        embs = embeddings
        if embs is None:
            embs = self._embedding_function(documents)
        for i, rec_id in enumerate(ids):
            self._records[rec_id] = _Record(
                document=documents[i],
                metadata=dict(metas[i]),
                embedding=list(embs[i]),
            )

    def update(
        self,
        ids: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        metas = metadatas or []
        for i, rec_id in enumerate(ids):
            rec = self._records.get(rec_id)
            if rec is None:
                continue
            if i < len(metas):
                rec.metadata.update(metas[i])

    def count(self) -> int:
        return len(self._records)

    def get(
        self,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
        limit: int | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        include_fields = set(include or ["documents", "metadatas"])
        result_ids: list[str] = []
        docs: list[str] = []
        metas: list[dict[str, Any]] = []
        embs: list[list[float]] = []

        ordered_ids = ids if ids is not None else list(self._records.keys())
        for rec_id in ordered_ids:
            rec = self._records.get(rec_id)
            if rec is None:
                continue
            if not _match_where(rec.metadata, where):
                continue
            result_ids.append(rec_id)
            docs.append(rec.document)
            metas.append(dict(rec.metadata))
            embs.append(list(rec.embedding))
            if limit is not None and len(result_ids) >= limit:
                break

        out: dict[str, Any] = {"ids": result_ids}
        if "documents" in include_fields:
            out["documents"] = docs
        if "metadatas" in include_fields:
            out["metadatas"] = metas
        if "embeddings" in include_fields:
            out["embeddings"] = embs
        return out

    def query(
        self,
        query_texts: list[str] | None = None,
        query_embeddings: list[list[float]] | None = None,
        n_results: int = 5,
        where: dict[str, Any] | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        include_fields = set(include or ["documents", "metadatas", "distances"])
        if query_embeddings is not None and len(query_embeddings) > 0:
            q = query_embeddings[0]
        elif query_texts is not None and len(query_texts) > 0:
            q = self._embedding_function([query_texts[0]])[0]
        else:
            q = []

        scored: list[tuple[str, float, _Record]] = []
        for rec_id, rec in self._records.items():
            if not _match_where(rec.metadata, where):
                continue
            scored.append((rec_id, _cosine_distance(q, rec.embedding), rec))
        scored.sort(key=lambda x: x[1])
        top = scored[: max(0, n_results)]

        ids = [x[0] for x in top]
        docs = [x[2].document for x in top]
        metas = [dict(x[2].metadata) for x in top]
        dists = [x[1] for x in top]

        out: dict[str, Any] = {"ids": [ids]}
        if "documents" in include_fields:
            out["documents"] = [docs]
        if "metadatas" in include_fields:
            out["metadatas"] = [metas]
        if "distances" in include_fields:
            out["distances"] = [dists]
        return out


_STORE_BY_PATH: dict[str, dict[str, Collection]] = {}


class PersistentClient:
    """Path-scoped in-memory client compatible with required APIs."""

    def __init__(self, path: str) -> None:
        self._path = path
        _STORE_BY_PATH.setdefault(path, {})

    def get_or_create_collection(
        self, name: str, embedding_function: Any
    ) -> Collection:
        collections = _STORE_BY_PATH[self._path]
        if name not in collections:
            collections[name] = Collection(embedding_function)
        return collections[name]
