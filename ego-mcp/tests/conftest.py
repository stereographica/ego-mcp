"""Shared test fixtures for ego-mcp."""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _cleanup_chromadb_systems() -> Iterator[None]:
    """Ensure ChromaDB systems are stopped between tests to avoid FD leaks."""
    yield
    try:
        from chromadb.api.shared_system_client import SharedSystemClient
    except Exception:
        return

    systems = list(SharedSystemClient._identifier_to_system.values())
    for system in systems:
        try:
            system.stop()
        except Exception:
            pass
    SharedSystemClient.clear_system_cache()
