# Project Overview

- Workspace root contains multiple directories (`ego-mcp`, `embodied-claude`, `tasks`, `design`), but the active Python package is `ego-mcp`.
- `ego-mcp` is an MCP server providing cognitive scaffolding tools for AI personality continuity.
- Main runtime entrypoint is `python -m ego_mcp` (`src/ego_mcp/__main__.py`), which runs async server startup from `ego_mcp.server`.
- Server exposes 15 tools: 7 surface tools and 8 backend tools.

## Tech Stack

- Python 3.11+
- Packaging/build: Hatchling (`pyproject.toml`)
- Environment/dependency manager: `uv`
- MCP SDK: `mcp>=1.0.0`
- Vector/memory backend dependency: `chromadb`
- HTTP client: `httpx`
- System info: `psutil`
- Testing: `pytest`, `pytest-asyncio`, `respx`
- Type checking: `mypy` in strict mode

## Rough Code Structure (`ego-mcp`)

- `src/ego_mcp/server.py`: MCP server, tool registration, request dispatch, and tool handlers.
- `src/ego_mcp/config.py`: config loading/validation from environment variables.
- `src/ego_mcp/memory.py`: memory storage/retrieval logic.
- `src/ego_mcp/desire.py`: desire state/engine.
- `src/ego_mcp/embedding.py`: embedding provider abstraction.
- `src/ego_mcp/scaffolds.py`: response scaffolding templates.
- `src/ego_mcp/types.py`: core dataclasses/enums.
- `tests/`: unit/integration tests by module.

## Configuration Notes

- Required API key depends on provider:
  - default provider `gemini` needs `GEMINI_API_KEY`
  - `openai` provider needs `OPENAI_API_KEY`
- Data directory defaults to `~/.ego-mcp/data` and is configurable via `EGO_MCP_DATA_DIR`.
- Companion naming configurable via `EGO_MCP_COMPANION_NAME`.