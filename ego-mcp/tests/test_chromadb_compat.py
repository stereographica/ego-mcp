"""Regression tests for ChromaDB compatibility on Python 3.14."""

from __future__ import annotations

from pathlib import Path

import ego_mcp.server as server_mod
from ego_mcp.chromadb_compat import load_chromadb
from ego_mcp.config import EgoConfig


def test_load_chromadb_prefers_real_module() -> None:
    """Compatibility shim should load real chromadb, not fallback module."""
    chromadb = load_chromadb()
    assert chromadb.__name__ == "chromadb"


def test_init_server_uses_real_chromadb_client(tmp_path: Path) -> None:
    """Server initialization should construct a real chromadb client."""
    config = EgoConfig(
        embedding_provider="gemini",
        embedding_model="gemini-embedding-001",
        api_key="test-key",
        data_dir=tmp_path / "ego-data",
        companion_name="Master",
        workspace_dir=None,
    )

    server_mod.init_server(config)
    assert server_mod._memory is not None
    client = server_mod._memory.get_client()
    assert client.__class__.__module__.startswith("chromadb.")
