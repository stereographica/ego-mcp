# ego-mcp

> Cognitive scaffolding MCP server for LLM personality continuity.

ego-mcp provides AI agents with persistent memory, abstract desires, and cognitive scaffolding — enabling more natural and continuous personality expression across sessions.

## Features

- **7 Surface Tools** — `wake_up`, `feel_desires`, `introspect`, `consider_them`, `remember`, `recall`, `am_i_being_genuine`
- **9 Backend Tools** — `satisfy_desire`, `consolidate`, `forget`, `link_memories`, `update_relationship`, `update_self`, `emotion_trend`, `get_episode`, `create_episode`
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
uv run python -c "import ego_mcp; print(ego_mcp.__version__)"  # → 0.6.2
uv run python -m ego_mcp  # Starts the server
```

### 4. Desire Catalog

Starting with `ego-mcp` v0.6.0, fixed desire definitions are stored in `${EGO_MCP_DATA_DIR}/settings/desires.json`.
If `settings/` or `settings/desires.json` does not exist at startup, the server generates the current default file directly from the Python schema.

State is now stored separately in `${EGO_MCP_DATA_DIR}/desire_state.json`.
The old `${EGO_MCP_DATA_DIR}/desires.json` from v0.5.x and earlier is treated as legacy state and safely copied into `desire_state.json` on first startup.

`settings/desires.json` overview:

```json
{
  "version": 1,
  "fixed_desires": {
    "information_hunger": {
      "display_name": "information hunger",
      "satisfaction_hours": 12,
      "maslow_level": 1,
      "sentence": {
        "medium": "You want to take something in.",
        "high": "You're starving for input."
      },
      "implicit_satisfaction": {
        "recall": 0.3
      }
    }
  },
  "implicit_rules": [
    {
      "tool": "remember",
      "when": {"category": "introspection"},
      "effects": [{"id": "cognitive_coherence", "quality": 0.4}]
    }
  ],
  "emergent": {
    "satisfaction_hours": 24,
    "expiry_hours": 72,
    "satisfied_ttl_hours": 168
  }
}
```

`settings/desires.json` schema reference:

Top-level keys:

| Key | Type | Required | Description |
|---|---|---|---|
| `version` | integer | Yes | Schema version. The current and only valid value is `1`. |
| `fixed_desires` | object | Yes | Map of fixed desire IDs to their configuration. The object key itself is the desire ID used internally by `ego-mcp`, the dashboard, telemetry, and `satisfy_desire`. |
| `implicit_rules` | array | Yes | Conditional implicit-satisfaction rules that apply only when a tool call matches a specific condition. Use this for cases that cannot be expressed by a simple per-tool mapping inside one desire. |
| `emergent` | object | Yes | Timing parameters for emergent desires that are generated from notions rather than listed in `fixed_desires`. |

`fixed_desires` entry keys:

| Key | Type | Required | Description |
|---|---|---|---|
| `fixed_desires.<desire_id>` | object | Yes | One fixed desire definition. `<desire_id>` must be a JSON object key such as `information_hunger` or `social_thirst`. This ID is the canonical identifier used in code and stored state. |
| `display_name` | string or null | No | Human-readable label used in the dashboard. If omitted, the default catalog uses the desire ID with underscores replaced by spaces. |
| `satisfaction_hours` | number | Yes | How long the desire takes to naturally rise back toward full pressure after being satisfied. Must be greater than `0`. Smaller values make the desire return faster. |
| `maslow_level` | integer | Yes | Ordering/grouping level for fixed desires. Must be `>= 1`. The dashboard sorts fixed desires by `(maslow_level, id)`. |
| `sentence` | object | Yes | Language templates used by deterministic desire blending in `wake_up`, `feel_desires`, `introspect`, and dashboard summaries. |
| `implicit_satisfaction` | object | No | Map from tool name to implicit satisfaction quality for this desire. Each key is a tool name such as `recall` or `consider_them`; each value must be within `0 < quality <= 1`. If omitted, it defaults to an empty object. |

`fixed_desires.<desire_id>.sentence` keys:

| Key | Type | Required | Description |
|---|---|---|---|
| `medium` | string | Yes | Sentence used when the desire is present but not at the highest pressure tier. |
| `high` | string | Yes | Sentence used when the desire is one of the strongest current pressures. |

`implicit_rules` entry keys:

| Key | Type | Required | Description |
|---|---|---|---|
| `tool` | string | Yes | Tool name that activates the rule, for example `remember`. |
| `when` | object | No | Additional match conditions. If omitted, the rule applies to every call of `tool`. |
| `effects` | array | Yes | List of desire effects applied when the rule matches. Must contain at least one item. |

`implicit_rules[].when` keys:

| Key | Type | Required | Description |
|---|---|---|---|
| `category` | string or null | No | Restricts the rule to tool calls with the given category. The built-in default uses this to apply a `remember` rule only when `category` is `introspection`. |

`implicit_rules[].effects[]` keys:

| Key | Type | Required | Description |
|---|---|---|---|
| `id` | string | Yes | Fixed desire ID to satisfy when the rule matches. If the ID does not exist in `fixed_desires`, the effect is ignored at runtime. |
| `quality` | number | Yes | Implicit satisfaction quality for the effect. Must be within `0 < quality <= 1`. |

`emergent` keys:

| Key | Type | Required | Description |
|---|---|---|---|
| `satisfaction_hours` | number | Yes | Recovery time constant for emergent desires after they are satisfied. Must be greater than `0`. |
| `expiry_hours` | number | Yes | How long an emergent desire can remain unsatisfied before it is considered stale and removed. Must be greater than `0`. |
| `satisfied_ttl_hours` | number | Yes | How long a satisfied emergent desire is retained before being removed from state. Must be greater than `0`. |

Validation and parsing rules:

- All objects use a strict schema. Unknown keys are rejected.
- `fixed_desires` IDs are free-form JSON keys, but they are treated as canonical internal IDs once chosen.
- `implicit_satisfaction` values and `implicit_rules[].effects[].quality` must always stay within `0 < quality <= 1`.
- `satisfaction_hours`, `expiry_hours`, and `satisfied_ttl_hours` must always be greater than `0`.
- `maslow_level` must always be `1` or greater.
- The file is created automatically from the Python schema when it does not exist.

Editing rules:

- Only desires that remain in `fixed_desires` are treated as existing.
- If you omit a built-in desire, it is hidden in both `ego-mcp` and the dashboard, and any historical state for it is treated as nonexistent.
- You can adjust the wording, `satisfaction_hours`, and `implicit_satisfaction` of built-in desires.
- You can add custom fixed desires under `fixed_desires`.
- `sentence.medium` and `sentence.high` are reflected in the blended language used by the dashboard, `wake_up`, `feel_desires`, and `introspect`.

If the settings violate the schema:

- The server still starts.
- `wake_up`, `feel_desires`, `introspect`, and `satisfy_desire` return an MCP tool error so the LLM can see the configuration problem.
- Tools such as `remember`, where desire updates are only a side effect, continue their main work and skip only the implicit desire update.

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
| `forget` | Delete a memory by ID |
| `link_memories` | Link two memories |
| `update_relationship` | Update relationship model |
| `update_self` | Update self model |
| `emotion_trend` | Analyze emotional patterns over time |
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

### Upgrading from v0.5.x

When upgrading from v0.5.x or earlier, you do not need to delete the existing `${EGO_MCP_DATA_DIR}/desires.json`.
v0.6.0 reads that file as legacy state and migrates it into `${EGO_MCP_DATA_DIR}/desire_state.json`.
The dashboard also reads `${EGO_MCP_DATA_DIR}/settings/desires.json` as the source of truth for the fixed desire catalog.

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
