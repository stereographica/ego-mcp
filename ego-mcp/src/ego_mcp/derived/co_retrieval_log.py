"""Co-retrieval append log (P1 S1).

The server appends one line per ``recall`` that returned two or more
(non-Proust) memories; the batch only reads. Writing never raises — a failed
append must not break a recall.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from ego_mcp.derived.contract import derived_dir

logger = logging.getLogger(__name__)

CO_RETRIEVAL_LOG_FILENAME = "co_retrieval.jsonl"
CO_RETRIEVAL_LOG_MAX = 5000

#: Counting lines on every append would make recall pay for the whole log, so
#: the size check runs once every ``_LINE_CHECK_INTERVAL`` appends.
_LINE_CHECK_INTERVAL = 100

_append_counter = 0


def co_retrieval_path(data_dir: Path) -> Path:
    """Return the on-disk path of the co-retrieval log (not created)."""
    return derived_dir(data_dir) / CO_RETRIEVAL_LOG_FILENAME


def append_co_retrieval(
    data_dir: Path, memory_ids: list[str], *, now: datetime
) -> None:
    """Append one recall's returned ids. Silently does nothing on failure."""
    global _append_counter

    ids = [memory_id for memory_id in memory_ids if isinstance(memory_id, str) and memory_id]
    if len(ids) < 2:
        return

    path = co_retrieval_path(data_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"at": now.isoformat(), "ids": ids}, ensure_ascii=False)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except (OSError, TypeError, ValueError) as exc:
        logger.debug("Co-retrieval append failed: %s", exc)
        return

    _append_counter += 1
    if _append_counter % _LINE_CHECK_INTERVAL != 0:
        return
    try:
        _trim_if_needed(path)
    except OSError as exc:
        logger.debug("Co-retrieval trim failed: %s", exc)


def _trim_if_needed(path: Path) -> None:
    """Rewrite the log to its newest ``CO_RETRIEVAL_LOG_MAX`` lines when over cap."""
    with path.open("r", encoding="utf-8") as handle:
        lines = handle.readlines()
    if len(lines) <= CO_RETRIEVAL_LOG_MAX:
        return
    kept = lines[-CO_RETRIEVAL_LOG_MAX:]
    tmp_path = path.parent / f".{path.name}.tmp"
    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            for line in kept:
                handle.write(line if line.endswith("\n") else line + "\n")
        os.replace(tmp_path, path)
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def read_co_retrieval(data_dir: Path) -> list[tuple[datetime, list[str]]]:
    """Read the log, skipping every line that does not parse."""
    path = co_retrieval_path(data_dir)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []

    entries: list[tuple[datetime, list[str]]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        at_raw = payload.get("at")
        if not isinstance(at_raw, str):
            continue
        try:
            at = datetime.fromisoformat(at_raw)
        except ValueError:
            continue
        ids_raw = payload.get("ids")
        if not isinstance(ids_raw, list):
            continue
        ids = [
            memory_id
            for memory_id in ids_raw
            if isinstance(memory_id, str) and memory_id
        ]
        if not ids:
            continue
        entries.append((at, ids))
    return entries


def _reset_counter_for_tests() -> None:
    """Reset the module append counter (tests only)."""
    global _append_counter
    _append_counter = 0
