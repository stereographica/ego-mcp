"""Derived layer: batch-computed shape of the memory store.

The batch measures *where to look* (ids, counts, distances, dates); it never
says *what it means*. It writes only under ``${EGO_MCP_DATA_DIR}/derived/`` and
never touches the primary stores. Deleting the whole directory is safe — the
next batch regenerates it.
"""

from __future__ import annotations

from ego_mcp.derived.co_retrieval_log import (
    CO_RETRIEVAL_LOG_FILENAME,
    CO_RETRIEVAL_LOG_MAX,
    append_co_retrieval,
    read_co_retrieval,
)
from ego_mcp.derived.config import DerivedConfig
from ego_mcp.derived.contract import (
    DERIVED_DEFAULT_TTL_HOURS,
    DERIVED_DIR_NAME,
    DERIVED_SCHEMA_VERSION,
    DERIVED_SURFACED_FILENAME,
    DERIVED_SURFACED_MAX,
    DerivedFile,
    DerivedReader,
    read_lens_file,
    write_lens_file,
)
from ego_mcp.derived.graph import (
    MemoryGraph,
    build_memory_graph,
    centroid,
    cosine_distance,
    has_path_within,
)
from ego_mcp.derived.lenses import LENSES, Lens, discover_lenses, register_lens
from ego_mcp.derived.source import (
    DERIVED_CHROMA_PAGE,
    DERIVED_MAX_MEMORIES,
    SnapshotUnavailable,
    SourceSnapshot,
    load_snapshot,
)
from ego_mcp.derived.words import count_words, span_words

__all__ = [
    "CO_RETRIEVAL_LOG_FILENAME",
    "CO_RETRIEVAL_LOG_MAX",
    "DERIVED_CHROMA_PAGE",
    "DERIVED_DEFAULT_TTL_HOURS",
    "DERIVED_DIR_NAME",
    "DERIVED_MAX_MEMORIES",
    "DERIVED_SCHEMA_VERSION",
    "DERIVED_SURFACED_FILENAME",
    "DERIVED_SURFACED_MAX",
    "LENSES",
    "DerivedConfig",
    "DerivedFile",
    "DerivedReader",
    "Lens",
    "MemoryGraph",
    "SnapshotUnavailable",
    "SourceSnapshot",
    "append_co_retrieval",
    "build_memory_graph",
    "centroid",
    "cosine_distance",
    "count_words",
    "discover_lenses",
    "has_path_within",
    "load_snapshot",
    "read_co_retrieval",
    "read_lens_file",
    "register_lens",
    "span_words",
    "write_lens_file",
]
