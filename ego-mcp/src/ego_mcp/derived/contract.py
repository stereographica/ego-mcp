"""File contract for the derived layer (D0 S2 / S3).

The batch owns ``derived/{lens}.json``; the server owns ``derived/surfaced.json``.
Both sides write atomically (temp file + :func:`os.replace`) because the server
and the batch can run concurrently.

Nothing in this module raises on malformed input: a missing, corrupt, stale or
schema-mismatched derived file is simply "no derived data today".
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DERIVED_SCHEMA_VERSION = 1
DERIVED_DIR_NAME = "derived"
DERIVED_SURFACED_FILENAME = "surfaced.json"
DERIVED_SURFACED_MAX = 2000
DERIVED_DEFAULT_TTL_HOURS = 36.0


@dataclass(frozen=True)
class DerivedFile:
    """One lens output file."""

    lens: str
    generated_at: str
    valid_until: str
    source: dict[str, int]
    items: list[dict[str, Any]]


def derived_dir(data_dir: Path) -> Path:
    """Return the derived directory for a data directory (not created)."""
    return data_dir / DERIVED_DIR_NAME


def lens_path(data_dir: Path, lens: str) -> Path:
    """Return the on-disk path of a lens file (not created)."""
    return derived_dir(data_dir) / f"{lens}.json"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON to ``path`` via a sibling temp file and :func:`os.replace`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.parent / f".{path.name}.tmp"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        tmp_path.write_text(text, encoding="utf-8")
        os.replace(tmp_path, path)
    except BaseException:
        # Never leave a half-written temp file behind; the real name is
        # untouched because os.replace either happened or did not.
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def write_lens_file(data_dir: Path, file: DerivedFile) -> Path:
    """Write one lens file atomically and return its path."""
    path = lens_path(data_dir, file.lens)
    _atomic_write_json(
        path,
        {
            "schema": DERIVED_SCHEMA_VERSION,
            "lens": file.lens,
            "generated_at": file.generated_at,
            "valid_until": file.valid_until,
            "source": dict(file.source),
            "items": list(file.items),
        },
    )
    return path


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def read_lens_file(data_dir: Path, lens: str, *, now: datetime) -> DerivedFile | None:
    """Read one lens file, or return ``None`` for every failure mode.

    ``None`` is returned when the file is missing, unreadable, not JSON, of an
    unexpected schema version, written for another lens, has an unparsable or
    already elapsed ``valid_until``, or carries a non-list ``items``. Items that
    are not dicts, or that lack a string ``key``, are skipped individually.
    """
    path = lens_path(data_dir, lens)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.debug("Derived file unreadable (%s): %s", path, exc)
        return None

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.debug("Derived file is not valid JSON (%s): %s", path, exc)
        return None

    if not isinstance(payload, dict):
        logger.debug("Derived file is not an object (%s)", path)
        return None

    if payload.get("schema") != DERIVED_SCHEMA_VERSION:
        logger.debug("Derived file schema mismatch (%s)", path)
        return None

    if payload.get("lens") != lens:
        logger.debug("Derived file lens mismatch (%s)", path)
        return None

    valid_until_raw = payload.get("valid_until")
    valid_until = _parse_iso(valid_until_raw)
    if valid_until is None:
        logger.debug("Derived file valid_until unparsable (%s)", path)
        return None

    comparable_now = now
    if valid_until.tzinfo is None and now.tzinfo is not None:
        valid_until = valid_until.replace(tzinfo=now.tzinfo)
    elif valid_until.tzinfo is not None and now.tzinfo is None:
        comparable_now = now.replace(tzinfo=valid_until.tzinfo)
    if valid_until <= comparable_now:
        logger.debug("Derived file expired (%s)", path)
        return None

    items_raw = payload.get("items")
    if not isinstance(items_raw, list):
        logger.debug("Derived file items is not a list (%s)", path)
        return None

    items: list[dict[str, Any]] = []
    for item in items_raw:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if not isinstance(key, str) or not key:
            continue
        items.append(item)

    source_raw = payload.get("source")
    source: dict[str, int] = {}
    if isinstance(source_raw, dict):
        for name, value in source_raw.items():
            if isinstance(value, int) and not isinstance(value, bool):
                source[str(name)] = value

    generated_at = payload.get("generated_at")
    return DerivedFile(
        lens=lens,
        generated_at=generated_at if isinstance(generated_at, str) else "",
        valid_until=valid_until_raw if isinstance(valid_until_raw, str) else "",
        source=source,
        items=items,
    )


class DerivedReader:
    """The server's only entry point into the derived layer.

    A fresh instance is built per call because the batch replaces the files
    underneath a running server.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)

    @property
    def surfaced_path(self) -> Path:
        return derived_dir(self._data_dir) / DERIVED_SURFACED_FILENAME

    def items(
        self,
        lens: str,
        *,
        now: datetime,
        exclude_surfaced: bool = True,
    ) -> list[dict[str, Any]]:
        """Return the lens items, in file order, optionally minus surfaced keys.

        Duplicate keys collapse to a single entry: the last occurrence wins on
        content, the first occurrence decides the position (ranking belongs to
        the batch, so the earlier slot is the conservative one to keep).
        """
        file = read_lens_file(self._data_dir, lens, now=now)
        if file is None:
            return []

        marks = self._load_marks() if exclude_surfaced else {}
        collapsed: dict[str, dict[str, Any]] = {}
        for item in file.items:
            key = str(item["key"])
            if exclude_surfaced and key in marks:
                continue
            collapsed[key] = item
        return list(collapsed.values())

    def marks(self) -> dict[str, str]:
        """Return a copy of all surfaced marks (key -> ISO timestamp)."""
        return dict(self._load_marks())

    def is_surfaced(self, key: str) -> bool:
        """Return whether ``key`` has already been presented."""
        return key in self._load_marks()

    def has_surfaced_with_prefix(self, prefix: str, *, suffix: str = "") -> bool:
        """Return whether any mark starts with ``prefix`` and ends with ``suffix``.

        Used for "at most one per day" gates (D1): the prefix names the lens and
        the suffix names the calendar day.
        """
        for key in self._load_marks():
            if key.startswith(prefix) and key.endswith(suffix):
                return True
        return False

    def last_surfaced_at(self, prefix: str) -> datetime | None:
        """Return the most recent mark timestamp among keys starting with ``prefix``.

        Used for presentation cooldowns (D4): the prefix names the lens and the
        subject (e.g. ``"drift:notion_ab12cd34"``).
        """
        stamps = [
            marked_at
            for key, marked_at in self._load_marks().items()
            if key.startswith(prefix) and _parse_iso(marked_at) is not None
        ]
        if not stamps:
            return None
        # Marks are written by mark_surfaced with a single timezone, so the ISO
        # strings order the same way the datetimes do — the same ordering the
        # cap eviction uses.
        return _parse_iso(max(stamps))

    def mark_surfaced(self, key: str, *, now: datetime) -> None:
        """Record ``key`` as presented, evicting the oldest marks past the cap."""
        marks = self._load_marks()
        marks[key] = now.isoformat()
        if len(marks) > DERIVED_SURFACED_MAX:
            ordered = sorted(marks.items(), key=lambda pair: pair[1])
            for stale_key, _ in ordered[: len(marks) - DERIVED_SURFACED_MAX]:
                marks.pop(stale_key, None)
        _atomic_write_json(
            self.surfaced_path,
            {"schema": DERIVED_SCHEMA_VERSION, "marks": marks},
        )

    def _load_marks(self) -> dict[str, str]:
        """Load surfaced marks; a corrupt file reads as empty (D4 edge cases)."""
        try:
            raw = self.surfaced_path.read_text(encoding="utf-8")
        except OSError:
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("surfaced.json is not valid JSON; treating as empty")
            return {}
        if not isinstance(payload, dict):
            return {}
        marks_raw = payload.get("marks")
        if not isinstance(marks_raw, dict):
            return {}
        return {
            str(key): value
            for key, value in marks_raw.items()
            if isinstance(value, str)
        }
