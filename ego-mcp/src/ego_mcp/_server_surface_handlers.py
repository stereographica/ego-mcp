"""Compatibility exports for surface handlers."""

from __future__ import annotations

from ego_mcp._server_surface_attune import _handle_attune
from ego_mcp._server_surface_core import (
    _handle_consider_them,
    _handle_introspect,
    _handle_pause,
    _handle_wake_up,
)
from ego_mcp._server_surface_memory import (
    _REMEMBER_DUPLICATE_PREFIX,
    _handle_recall,
    _handle_remember,
)

__all__ = [
    "_REMEMBER_DUPLICATE_PREFIX",
    "_handle_wake_up",
    "_handle_attune",
    "_handle_introspect",
    "_handle_consider_them",
    "_handle_remember",
    "_handle_recall",
    "_handle_pause",
]
