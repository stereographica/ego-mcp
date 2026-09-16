"""The lens registry registers every lens exactly once, in roadmap order."""

from __future__ import annotations

import importlib
from collections.abc import Iterator

import pytest

from ego_mcp.derived.lenses import LENSES

EXPECTED_ORDER = [
    "recurrence",
    "dream",
    "holes",
    "drift",
    "chapters",
    "affect",
    "stagnation",
    "coretrieval",
    "rereading",
]


@pytest.fixture
def fresh_registry() -> Iterator[None]:
    saved = dict(LENSES)
    LENSES.clear()
    try:
        yield
    finally:
        LENSES.clear()
        LENSES.update(saved)


def test_registry_registers_all_lenses_in_order(fresh_registry: None) -> None:
    importlib.reload(importlib.import_module("ego_mcp.derived._registry"))
    assert list(LENSES) == EXPECTED_ORDER


def test_reimport_is_idempotent(fresh_registry: None) -> None:
    module = importlib.import_module("ego_mcp.derived._registry")
    importlib.reload(module)
    before = dict(LENSES)
    importlib.reload(module)
    assert dict(LENSES) == before
