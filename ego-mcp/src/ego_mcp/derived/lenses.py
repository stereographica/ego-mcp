"""Lens protocol and registry (D0 S6).

A lens measures the *shape* of the memory store and emits ids, numbers and
mechanism vocabulary — never prose, never a link, never a notion. ``compute``
must be a pure function of the snapshot: no file reads, no writes, and any
randomness seeded from ``snapshot.now`` so a second run on the same day gives
the same answer.

The registry starts empty. Lens modules register themselves from
``ego_mcp.derived._registry`` (see :func:`discover_lenses`), so adding a lens
never means editing this file.
"""

from __future__ import annotations

import importlib
import logging
import re
from typing import Any, Protocol

from ego_mcp.derived.source import SourceSnapshot

logger = logging.getLogger(__name__)

LENS_NAME_PATTERN = re.compile(r"^[a-z_]+$")

#: Module imported by :func:`discover_lenses`; importing it must register every
#: lens by calling :func:`register_lens`. It does not exist yet.
LENS_REGISTRY_MODULE = "ego_mcp.derived._registry"


class Lens(Protocol):
    """One derived measurement."""

    #: Registry key and file name stem; must match ``^[a-z_]+$``.
    name: str
    #: Whether the snapshot must carry embeddings for this lens.
    needs_embeddings: bool
    #: How long the written file stays valid.
    ttl_hours: float

    def compute(self, snapshot: SourceSnapshot) -> list[dict[str, Any]]:
        """Return the lens items; each must carry a stable string ``key``."""
        ...


LENSES: dict[str, Lens] = {}


def register_lens(lens: Lens) -> Lens:
    """Register a lens under its ``name``.

    Raises:
        ValueError: if the name is malformed or already registered.
    """
    name = getattr(lens, "name", "")
    if not isinstance(name, str) or not LENS_NAME_PATTERN.match(name):
        raise ValueError(
            f"Invalid lens name: {name!r}. Lens names must match ^[a-z_]+$."
        )
    if name in LENSES:
        raise ValueError(f"Lens '{name}' is already registered.")
    LENSES[name] = lens
    return lens


def lens_stats(lens: Lens) -> dict[str, int]:
    """Return the optional ``stats`` a lens populated during ``compute``.

    Lenses may expose a ``stats: dict[str, int]`` attribute with behavioural
    evidence counters; the CLI merges it into the completion log extra.
    """
    stats = getattr(lens, "stats", None)
    if not isinstance(stats, dict):
        return {}
    return {
        str(key): value
        for key, value in stats.items()
        if isinstance(value, int) and not isinstance(value, bool)
    }


def discover_lenses() -> None:
    """Import the lens registry module if it exists.

    Keeps ``lenses.py`` free of imports of individual lens modules: each lens
    module is imported by ``ego_mcp.derived._registry``, which registers them in
    roadmap implementation order. A missing module simply means no lenses.
    """
    try:
        importlib.import_module(LENS_REGISTRY_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name != LENS_REGISTRY_MODULE:
            # The registry exists but one of its imports is broken: that is a
            # real failure, not "no lenses installed".
            raise
        logger.debug(
            "No lens registry module (%s); registry left as is",
            LENS_REGISTRY_MODULE,
        )
