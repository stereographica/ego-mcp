"""Shared test fixtures for ego-mcp."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _cleanup_chromadb_systems() -> None:
    """Ensure ChromaDB systems are stopped between tests to avoid FD leaks."""
    yield
    try:
        from chromadb.api.shared_system_client import SharedSystemClient
    except Exception:
        return

    systems = list(SharedSystemClient._identifier_to_system.values())  # type: ignore[attr-defined]
    for system in systems:
        try:
            system.stop()
        except Exception:
            pass
    SharedSystemClient.clear_system_cache()
