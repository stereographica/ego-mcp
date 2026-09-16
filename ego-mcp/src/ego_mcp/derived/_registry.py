"""Lens registry — imported by :func:`ego_mcp.derived.lenses.discover_lenses`.

Registers every lens in roadmap implementation order. Lens modules never
register themselves so that importing one for tests has no side effects.
"""

from __future__ import annotations

from ego_mcp.derived.affect import AffectLens
from ego_mcp.derived.chapters import ChaptersLens
from ego_mcp.derived.co_retrieval import CoRetrievalLens
from ego_mcp.derived.dream import DreamLens
from ego_mcp.derived.drift import DriftLens
from ego_mcp.derived.holes import HolesLens
from ego_mcp.derived.lenses import LENSES, register_lens
from ego_mcp.derived.recurrence import RecurrenceLens
from ego_mcp.derived.rereading import RereadingLens
from ego_mcp.derived.stagnation import StagnationLens

_ORDERED_LENSES = (
    RecurrenceLens,
    DreamLens,
    HolesLens,
    DriftLens,
    ChaptersLens,
    AffectLens,
    StagnationLens,
    CoRetrievalLens,
    RereadingLens,
)

for _lens_cls in _ORDERED_LENSES:
    _instance = _lens_cls()
    if _instance.name not in LENSES:
        register_lens(_instance)
