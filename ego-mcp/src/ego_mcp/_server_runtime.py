"""Runtime accessors shared by server handlers."""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from pathlib import Path

from ego_mcp.episode import EpisodeStore
from ego_mcp.impulse import ImpulseManager
from ego_mcp.notion import NotionStore
from ego_mcp.workspace_sync import WorkspaceMemorySync


def _workspace_sync_default() -> WorkspaceMemorySync | None:
    return None


_workspace_sync_getter: Callable[[], WorkspaceMemorySync | None] = _workspace_sync_default
_episodes_getter: Callable[[], EpisodeStore] | None = None
_default_notion_store = NotionStore(Path("/tmp/ego-mcp-runtime-notions.json"))
_default_impulse_manager = ImpulseManager()


def _notion_store_default() -> NotionStore:
    return _default_notion_store


def _impulse_manager_default() -> ImpulseManager:
    return _default_impulse_manager


_notion_store_getter: Callable[[], NotionStore] = _notion_store_default
_impulse_manager_getter: Callable[[], ImpulseManager] = _impulse_manager_default
_tool_metadata: ContextVar[dict[str, object]] = ContextVar("tool_metadata", default={})
_tool_completion_metadata: dict[str, object] = {}


def configure_runtime_accessors(
    *,
    workspace_sync_getter: Callable[[], WorkspaceMemorySync | None],
    episodes_getter: Callable[[], EpisodeStore],
    notion_store_getter: Callable[[], NotionStore],
    impulse_manager_getter: Callable[[], ImpulseManager],
) -> None:
    """Register runtime accessors provided by server.py globals."""
    global _workspace_sync_getter, _episodes_getter, _notion_store_getter, _impulse_manager_getter
    _workspace_sync_getter = workspace_sync_getter
    _episodes_getter = episodes_getter
    _notion_store_getter = notion_store_getter
    _impulse_manager_getter = impulse_manager_getter


def get_workspace_sync() -> WorkspaceMemorySync | None:
    return _workspace_sync_getter()


def get_episodes() -> EpisodeStore:
    if _episodes_getter is None:
        raise RuntimeError("Episode store accessor is not configured")
    return _episodes_getter()


def get_notion_store() -> NotionStore:
    return _notion_store_getter()


def get_impulse_manager() -> ImpulseManager:
    return _impulse_manager_getter()


def reset_tool_metadata() -> None:
    _tool_metadata.set({})


def update_tool_metadata(**kwargs: object) -> None:
    current = dict(_tool_metadata.get())
    for key, value in kwargs.items():
        if value is None:
            continue
        current[key] = value
    _tool_metadata.set(current)


def get_tool_metadata() -> dict[str, object]:
    return dict(_tool_metadata.get())


def clear_tool_completion_metadata() -> None:
    _tool_completion_metadata.clear()


def update_tool_completion_metadata(**kwargs: object) -> None:
    _tool_completion_metadata.update(kwargs)


def take_tool_completion_metadata() -> dict[str, object]:
    payload = dict(_tool_completion_metadata)
    _tool_completion_metadata.clear()
    return payload
