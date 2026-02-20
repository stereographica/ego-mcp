# Suggested Commands

## Basic Navigation (Darwin/macOS shell)

- `pwd` : show current directory
- `ls -la` : list files (including hidden)
- `cd <path>` : move directories
- `find . -maxdepth 3 -type f` : inspect file tree
- `rg "<pattern>" ego-mcp` : fast text search
- `git status` : check working tree
- `git diff` : inspect changes

## Setup

- `cd ego-mcp`
- `uv sync --dev` : install runtime + dev dependencies

## Run / Verify

- `uv run python -c "import ego_mcp; print(ego_mcp.__version__)"` : sanity import/version check
- `uv run python -m ego_mcp` : run MCP server

## Tests / Type Check

- `uv run pytest tests/ -v` : run full test suite
- `uv run mypy src/ego_mcp/` : strict type check

## Environment Variable Examples

- `export GEMINI_API_KEY="..."`
- `export EGO_MCP_EMBEDDING_PROVIDER="openai"`
- `export OPENAI_API_KEY="..."`
- `export EGO_MCP_DATA_DIR="$HOME/.ego-mcp/data"`
- `export EGO_MCP_COMPANION_NAME="Master"`