# ego-mcp

> Cognitive scaffolding MCP server for LLM personality continuity.

ego-mcp provides AI agents with persistent memory, abstract desires, and cognitive scaffolding — enabling more natural and continuous personality expression across sessions.

## Features

- **7 Surface Tools** — `wake_up`, `feel_desires`, `introspect`, `consider_them`, `remember`, `recall`, `am_i_being_genuine`
- **8 Backend Tools** — `satisfy_desire`, `consolidate`, `link_memories`, `update_relationship`, `update_self`, `search_memories`, `get_episode`, `create_episode`
- **Progressive Disclosure** — Surface tools guide the AI to backend tools as needed
- **Cognitive Scaffolding** — Tool responses include thinking frameworks, not just data
- **All English Responses** — Saves 2-3x tokens compared to Japanese
- **Token Budget** — Tool definitions stay under ~1,500 tokens
- **Workspace Sync (optional)** — Syncs `remember` entries to OpenClaw Markdown memory files

## Quick Start

### 1. Install

```bash
cd ego-mcp
uv sync --dev
```

Alternative (pip):
```bash
cd ego-mcp
pip install -e .[dev]
```

### 2. Set Environment Variables

```bash
# Required: Choose one
export GEMINI_API_KEY="your-gemini-api-key"
# OR
export EGO_MCP_EMBEDDING_PROVIDER="openai"
export OPENAI_API_KEY="your-openai-api-key"
# Optional: enable OpenClaw workspace Markdown sync
export EGO_MCP_WORKSPACE_DIR="/path/to/openclaw-workspace"
```

### 3. Verify

```bash
uv run python -c "import ego_mcp; print(ego_mcp.__version__)"  # → 0.1.0
uv run python -m ego_mcp  # Starts the server
```

## Connecting to OpenClaw (via mcporter)

OpenClaw does **not** support a root-level `mcpServers` key in `~/.openclaw/openclaw.json`.
Use the bundled `mcporter` skill + mcporter config instead.

1. Enable `mcporter` in `~/.openclaw/openclaw.json`:

```json5
{
  skills: {
    entries: {
      mcporter: { enabled: true }
    }
  }
}
```

2. Add `ego` to mcporter config (`~/.mcporter/mcporter.json`):

```json
{
  "mcpServers": {
    "ego": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/ego-mcp", "python", "-m", "ego_mcp"],
      "env": {
        "GEMINI_API_KEY": "your-key-here",
        "EGO_MCP_WORKSPACE_DIR": "/path/to/openclaw-workspace"
      }
    }
  }
}
```

If you use a custom mcporter config path, pass it via OpenClaw skill env:

```json5
{
  skills: {
    entries: {
      mcporter: {
        enabled: true,
        env: { MCPORTER_CONFIG: "/absolute/path/to/mcporter.json" }
      }
    }
  }
}
```

### Verify `wake_up` via mcporter

1. `npx mcporter list ego`
2. `npx mcporter call ego.wake_up "{}"`
3. In OpenClaw, ask the agent to call `ego.wake_up` through `mcporter`.
4. Confirm the response contains:
   - last introspection summary (`No introspection yet.` on first run is expected)
   - desire summary
   - scaffold separator `---`

References:
- OpenClaw Skills Config: <https://docs.openclaw.ai/tools/skills-config>
- OpenClaw Skills: <https://docs.openclaw.ai/tools/skills>
- OpenClaw Configuration (strict validation): <https://docs.openclaw.ai/gateway/configuration>
- mcporter CLI/config: <https://github.com/flux159/mcporter>

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `EGO_MCP_EMBEDDING_PROVIDER` | `gemini` | `gemini` or `openai` |
| `EGO_MCP_EMBEDDING_MODEL` | Provider-dependent | Embedding model name |
| `GEMINI_API_KEY` | — | Required if provider is `gemini` |
| `OPENAI_API_KEY` | — | Required if provider is `openai` |
| `EGO_MCP_DATA_DIR` | `~/.ego-mcp/data` | Data storage directory |
| `EGO_MCP_COMPANION_NAME` | `Master` | Name used in scaffolding templates |
| `EGO_MCP_WORKSPACE_DIR` | — | OpenClaw workspace root for Markdown sync (`memory/YYYY-MM-DD.md`, `MEMORY.md`, `memory/inner-monologue-latest.md`) |

## Tool Overview

### Surface Tools (always visible)

| Tool | Description |
|---|---|
| `wake_up` | Start a session. Returns last introspection + desire summary |
| `feel_desires` | Check desire levels with action guidance |
| `introspect` | Get reflection materials: memories, desires, open questions |
| `consider_them` | Think about someone — ToM framework |
| `remember` | Save a memory with emotion and importance |
| `recall` | Recall related memories by context |
| `am_i_being_genuine` | Authenticity self-check |

### Backend Tools (guided by surface tools)

| Tool | Description |
|---|---|
| `satisfy_desire` | Mark a desire as satisfied |
| `consolidate` | Run memory consolidation |
| `link_memories` | Link two memories |
| `update_relationship` | Update relationship model |
| `update_self` | Update self model |
| `search_memories` | Search memories with filters |
| `get_episode` | Get episode details |
| `create_episode` | Create episode from memories |

## Workspace Guide

See [docs/workspace-guide.md](docs/workspace-guide.md) for how to configure SOUL.md, AGENTS.md, and HEARTBEAT.md.

## Development

```bash
# Run all tests
uv run pytest tests/ -v

# Type check
uv run mypy src/ego_mcp/
```

## Troubleshooting

### `hashlib blake2*` error when running `uv`

If you see errors like `unsupported hash type blake2b` / `blake2s`, `uv` is usually picking a broken Python build (often from `pyenv`).

This project pins Python via `.python-version` (`3.14`) to avoid that. Recreate your environment with:

```bash
cd ego-mcp
rm -rf .venv
uv sync --dev
```

If your shell still forces a broken `pyenv` interpreter, run explicitly once:

```bash
uv run --python /opt/homebrew/bin/python3.14 python -c "import hashlib; print(hasattr(hashlib, 'blake2b'))"
```
