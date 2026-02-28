"""Runtime accessors shared by server handlers."""

from __future__ import annotations

from collections.abc import Callable

from ego_mcp.episode import EpisodeStore
from ego_mcp.workspace_sync import WorkspaceMemorySync


def _workspace_sync_default() -> WorkspaceMemorySync | None:
    return None


_workspace_sync_getter: Callable[[], WorkspaceMemorySync | None] = _workspace_sync_default
_episodes_getter: Callable[[], EpisodeStore] | None = None


def configure_runtime_accessors(
    *,
    workspace_sync_getter: Callable[[], WorkspaceMemorySync | None],
    episodes_getter: Callable[[], EpisodeStore],
) -> None:
    """Register runtime accessors provided by server.py globals."""
    global _workspace_sync_getter, _episodes_getter
    _workspace_sync_getter = workspace_sync_getter
    _episodes_getter = episodes_getter


def get_workspace_sync() -> WorkspaceMemorySync | None:
    return _workspace_sync_getter()


def get_episodes() -> EpisodeStore:
    if _episodes_getter is None:
        raise RuntimeError("Episode store accessor is not configured")
    return _episodes_getter()
