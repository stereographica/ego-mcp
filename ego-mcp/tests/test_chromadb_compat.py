"""Regression tests for ChromaDB compatibility on Python 3.14."""

from __future__ import annotations

import typing
from pathlib import Path

import pytest

import ego_mcp.server as server_mod
from ego_mcp.chromadb_compat import (
    ensure_typing_bytestring_compat,
    load_chromadb,
)
from ego_mcp.config import EgoConfig


def test_load_chromadb_prefers_real_module() -> None:
    """Compatibility shim should load real chromadb, not fallback module."""
    chromadb = load_chromadb()
    assert chromadb.__name__ == "chromadb"


def test_ensure_typing_bytestring_compat_restores_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When typing.ByteString is missing (Python 3.14), it is restored."""
    monkeypatch.delattr(typing, "ByteString", raising=False)
    assert not hasattr(typing, "ByteString")
    ensure_typing_bytestring_compat()
    assert hasattr(typing, "ByteString")


def test_init_server_uses_real_chromadb_client(tmp_path: Path) -> None:
    """Server initialization should construct a real chromadb client."""
    config = EgoConfig(
        embedding_provider="gemini",
        embedding_model="gemini-embedding-001",
        api_key="test-key",
        data_dir=tmp_path / "ego-data",
        companion_name="Master",
        workspace_dir=None,
        timezone="UTC",
    )

    server_mod.init_server(config)
    assert server_mod._memory is not None
    client = server_mod._memory.get_client()
    assert client.__class__.__module__.startswith("chromadb.")
