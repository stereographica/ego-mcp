"""Compatibility helpers for ChromaDB on newer Python versions."""

from __future__ import annotations

import logging
import inspect
from types import ModuleType

logger = logging.getLogger(__name__)


def ensure_chromadb_pydantic_compat() -> None:
    """Ensure ChromaDB can import pydantic BaseSettings on Python 3.14.

    ChromaDB first tries `from pydantic import BaseSettings` and falls back to
    `pydantic.v1` if unavailable. The fallback currently breaks on Python 3.14.
    Providing `BaseSettings` from `pydantic_settings` keeps ChromaDB on the
    non-v1 branch.
    """
    try:
        import pydantic
        from pydantic_settings import BaseSettings
    except ImportError:
        return

    if inspect.getattr_static(pydantic, "BaseSettings", None) is None:
        setattr(pydantic, "BaseSettings", BaseSettings)


def load_chromadb() -> ModuleType:
    """Load ChromaDB module with a local fallback on import failure."""
    ensure_chromadb_pydantic_compat()
    try:
        import chromadb

        return chromadb
    except Exception as e:
        logger.warning(
            "Falling back to local_chromadb due to ChromaDB import error: %s", e
        )
        from ego_mcp import local_chromadb

        return local_chromadb
