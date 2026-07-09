"""SQLite FTS5 (trigram) lexical index for BM25-based keyword search.

This module backs the lexical half of the semantic + BM25 hybrid recall
pipeline. It is intentionally dependency-free (stdlib ``sqlite3`` only) and
degrades to a fully inert no-op mode whenever FTS5 or the trigram tokenizer
is unavailable in the running SQLite build, so recall never breaks due to
environment differences.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_TRIGRAMS = 64


def build_match_query(query: str) -> str:
    """Build an FTS5 ``MATCH`` expression from a raw, untrusted query string.

    The query is lowercased and split on whitespace/newlines. Each segment
    shorter than three characters is discarded; the rest are expanded into
    character trigrams. Trigrams are deduplicated (order-preserving) and
    capped at ``_MAX_TRIGRAMS`` via even-interval sampling. Each surviving
    trigram is escaped as an FTS5 double-quoted phrase (embedded ``"``
    doubled to ``""``) and joined with ``" OR "``.

    Treating every query as a bag of character trigrams means languages
    without whitespace segmentation (e.g. Japanese) are handled the same way
    as whitespace-segmented languages, and any FTS5 query syntax embedded in
    user input (``AND``/``OR``/``*``/``"``) is neutralized rather than
    interpreted.

    Returns an empty string when no trigram can be formed, signaling that no
    lexical search should be performed.
    """
    trigrams: list[str] = []
    seen: set[str] = set()
    for segment in query.lower().split():
        if len(segment) < 3:
            continue
        for i in range(len(segment) - 2):
            trigram = segment[i : i + 3]
            if trigram in seen:
                continue
            seen.add(trigram)
            trigrams.append(trigram)

    if not trigrams:
        return ""

    if len(trigrams) > _MAX_TRIGRAMS:
        step = len(trigrams) / _MAX_TRIGRAMS
        trigrams = [trigrams[int(i * step)] for i in range(_MAX_TRIGRAMS)]

    escaped = [f'"{trigram.replace(chr(34), chr(34) * 2)}"' for trigram in trigrams]
    return " OR ".join(escaped)


class LexicalIndex:
    """SQLite FTS5 (trigram) index used for BM25 lexical search.

    Synchronous by design: the server drives everything from a single
    asyncio event loop, so there is no need for async I/O here.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._conn: sqlite3.Connection | None = None
        self.available = False

    def connect(self) -> None:
        """Open the SQLite connection and create the FTS5 table if possible.

        Any failure (FTS5 missing, trigram tokenizer missing, filesystem
        error, ...) is caught and results in ``available=False`` rather than
        propagating, so a broken environment cannot break memory storage.
        """
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._path))
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts "
                "USING fts5(memory_id UNINDEXED, content, tokenize='trigram')"
            )
            conn.commit()
        except Exception as exc:
            logger.warning(
                "Lexical index unavailable, disabling BM25 search: %s", exc
            )
            self._conn = None
            self.available = False
            return
        self._conn = conn
        self.available = True

    def close(self) -> None:
        """Close the SQLite connection, if open. Safe to call repeatedly."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception as exc:
                logger.warning("Failed to close lexical index: %s", exc)
            self._conn = None

    def add(self, memory_id: str, content: str) -> None:
        """Index a memory's content. No-op if the index is unavailable."""
        if not self.available or self._conn is None:
            return
        try:
            self._conn.execute(
                "INSERT INTO memory_fts(memory_id, content) VALUES (?, ?)",
                (memory_id, content),
            )
            self._conn.commit()
        except Exception as exc:
            logger.warning(
                "Failed to index memory %s for lexical search: %s", memory_id, exc
            )

    def remove(self, memory_id: str) -> None:
        """Remove a memory from the index. No-op if the index is unavailable."""
        if not self.available or self._conn is None:
            return
        try:
            self._conn.execute(
                "DELETE FROM memory_fts WHERE memory_id = ?", (memory_id,)
            )
            self._conn.commit()
        except Exception as exc:
            logger.warning(
                "Failed to remove memory %s from lexical index: %s", memory_id, exc
            )

    def count(self) -> int:
        """Return the number of indexed rows (0 if the index is unavailable)."""
        if not self.available or self._conn is None:
            return 0
        try:
            row = self._conn.execute("SELECT count(*) FROM memory_fts").fetchone()
            return int(row[0]) if row is not None else 0
        except Exception as exc:
            logger.warning("Failed to count lexical index rows: %s", exc)
            return 0

    def rebuild(self, items: Iterable[tuple[str, str]]) -> None:
        """Replace the full index contents with ``items`` in one transaction.

        Used to bootstrap/self-heal the lexical index when it has drifted
        out of sync with the vector store (e.g. an existing installation
        upgrading into this feature).
        """
        if not self.available or self._conn is None:
            return
        try:
            with self._conn:
                self._conn.execute("DELETE FROM memory_fts")
                self._conn.executemany(
                    "INSERT INTO memory_fts(memory_id, content) VALUES (?, ?)",
                    list(items),
                )
        except Exception as exc:
            logger.warning("Failed to rebuild lexical index: %s", exc)

    def search(self, query: str, limit: int) -> list[str]:
        """Return memory_ids matching ``query``, ranked by BM25 (best first).

        Returns an empty list if the index is unavailable or no trigram
        could be built from ``query`` (i.e. every segment was shorter than
        three characters).
        """
        if not self.available or self._conn is None:
            return []
        match_expr = build_match_query(query)
        if not match_expr:
            return []
        try:
            rows = self._conn.execute(
                "SELECT memory_id FROM memory_fts WHERE memory_fts MATCH ? "
                "ORDER BY bm25(memory_fts) LIMIT ?",
                (match_expr, limit),
            ).fetchall()
            return [str(row[0]) for row in rows]
        except Exception as exc:
            logger.warning("Lexical search failed for query %r: %s", query, exc)
            return []
