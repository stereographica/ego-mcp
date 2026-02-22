"""End-to-end smoke tests via MCP SDK client over stdio."""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import InitializeResult, TextContent

EXPECTED_TOOL_NAMES = {
    "wake_up",
    "feel_desires",
    "introspect",
    "consider_them",
    "remember",
    "recall",
    "am_i_being_genuine",
    "satisfy_desire",
    "consolidate",
    "link_memories",
    "update_relationship",
    "update_self",
    "emotion_trend",
    "get_episode",
    "create_episode",
}


@asynccontextmanager
async def _open_session(
    tmp_path: Path,
) -> AsyncIterator[tuple[ClientSession, InitializeResult]]:
    """Start ego-mcp as a subprocess and return initialized SDK session."""
    repo_root = Path(__file__).resolve().parents[1]
    env = {
        **os.environ,
        "GEMINI_API_KEY": "test-key",
        "EGO_MCP_DATA_DIR": str(tmp_path / "ego-data"),
        "UV_CACHE_DIR": os.environ.get("UV_CACHE_DIR", "/tmp/uv-cache"),
    }
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ego_mcp"],
        cwd=str(repo_root),
        env=env,
    )

    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            init = await session.initialize()
            yield session, init


def _extract_texts(result: object) -> list[str]:
    contents = getattr(result, "content", [])
    return [item.text for item in contents if isinstance(item, TextContent)]


@pytest.mark.anyio
async def test_sdk_initialize_exposes_server_info(tmp_path: Path) -> None:
    async with _open_session(tmp_path) as (_session, init):
        assert init.serverInfo.name == "ego-mcp"


@pytest.mark.anyio
async def test_sdk_list_tools_matches_contract(tmp_path: Path) -> None:
    async with _open_session(tmp_path) as (session, _init):
        tools = await session.list_tools()
        assert {tool.name for tool in tools.tools} == EXPECTED_TOOL_NAMES


@pytest.mark.anyio
async def test_sdk_call_tool_returns_scaffolded_text(tmp_path: Path) -> None:
    async with _open_session(tmp_path) as (session, _init):
        result = await session.call_tool("am_i_being_genuine", {})
        texts = _extract_texts(result)
        assert len(texts) == 1
        assert "Self-check triggered." in texts[0]
        assert "---" in texts[0]


@pytest.mark.anyio
async def test_sdk_wake_up_smoke(tmp_path: Path) -> None:
    async with _open_session(tmp_path) as (session, _init):
        result = await session.call_tool("wake_up", {})
        texts = _extract_texts(result)
        assert len(texts) == 1
        assert "No introspection yet." in texts[0]
        assert "Desires:" in texts[0]
