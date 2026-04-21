"""Compatibility helpers for ChromaDB on newer Python versions."""

from __future__ import annotations

import collections.abc
import inspect
import logging
import typing
from types import ModuleType

logger = logging.getLogger(__name__)


def ensure_typing_bytestring_compat() -> None:
    """Restore ``typing.ByteString`` removed in Python 3.14.

    The ``overrides`` 7.7.0 transitive dependency references
    ``typing.ByteString`` at import time, which breaks on Python 3.14 where
    the alias has been removed. Re-aliasing it to ``collections.abc.Buffer``
    matches the migration recommended by PEP 688.
    """
    if not hasattr(typing, "ByteString"):
        setattr(typing, "ByteString", collections.abc.Buffer)


def ensure_chromadb_pydantic_compat() -> None:
    """Ensure ChromaDB config models can be created on Python 3.14.

    ChromaDB 1.5.x defines a few unannotated config class attributes that
    trigger hard errors with modern pydantic. We provide a compatible
    BaseSettings subclass that ignores unannotated plain builtins while keeping
    normal annotated fields intact.
    """
    try:
        import pydantic
        from pydantic_settings import BaseSettings as PydanticSettingsBase
        from pydantic_settings import (
            SettingsConfigDict,
        )
    except ImportError:
        return

    if inspect.getattr_static(pydantic, "BaseSettings", None) is None:

        class CompatBaseSettings(PydanticSettingsBase):
            model_config = SettingsConfigDict(
                ignored_types=(str, int, float, bool, list, dict, set, tuple)
            )

        setattr(pydantic, "BaseSettings", CompatBaseSettings)


def load_chromadb() -> ModuleType:
    """Load ChromaDB module with a local fallback on import failure."""
    ensure_typing_bytestring_compat()
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
