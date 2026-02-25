# ego-mcp

> Cognitive scaffolding platform that gives AI agents persistent personality, memory, and emotions.

ego-mcp is a monorepo containing an [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that enables LLM agents to maintain consistent personality, memory, and emotions across sessions, along with a telemetry dashboard for real-time observability.

## Key Features

- **Persistent Memory** — ChromaDB-based semantic search + Hopfield pattern completion for associative recall
- **Abstract Desire System** — Nonlinear computation with emotion/memory modulation for intrinsic motivation
- **Cognitive Scaffolding** — Tool responses include thinking frameworks, not just data, guiding natural AI behavior
- **Relationship Model** — Theory of Mind framework for structuring relationships with others
- **Telemetry Dashboard** — Real-time visualization of tool usage, emotion trends, and logs

## Repository Structure

```
ego-mcp/
├── ego-mcp/            # MCP server (Python)
├── dashboard/          # Telemetry dashboard
│   ├── src/            #   Backend (FastAPI + TimescaleDB + Redis)
│   └── frontend/       #   Frontend (React + Vite + TypeScript)
├── design/             # Design documents
└── .github/workflows/  # CI
```

## ego-mcp

MCP server providing cognitive capabilities to AI agents.

### Tools

**Surface Tools** — directly used by the agent:

| Tool | Description |
|---|---|
| `wake_up` | Start a session. Returns last introspection + desire summary |
| `feel_desires` | Check current desire levels with action guidance |
| `introspect` | Get reflection materials: memories, desires, open questions |
| `consider_them` | Think about someone — Theory of Mind framework |
| `remember` | Save a memory with emotion and importance |
| `recall` | Recall related memories by context |
| `am_i_being_genuine` | Authenticity self-check |

**Backend Tools** — guided by surface tools:

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

### Setup

```bash
cd ego-mcp
uv sync --extra dev
```

Set environment variables for the embedding provider:

```bash
# Gemini (default)
export GEMINI_API_KEY="your-gemini-api-key"

# OR OpenAI
export EGO_MCP_EMBEDDING_PROVIDER="openai"
export OPENAI_API_KEY="your-openai-api-key"
```

### Run

```bash
cd ego-mcp
uv run python -m ego_mcp
```

### Connecting to an MCP Client

Example configuration for Claude Desktop or other MCP-compatible clients:

```json
{
  "mcpServers": {
    "ego": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/ego-mcp", "python", "-m", "ego_mcp"],
      "env": {
        "GEMINI_API_KEY": "your-key-here"
      }
    }
  }
}
```

See [ego-mcp/README.md](ego-mcp/README.md) for full documentation including environment variables and workspace sync.

## Dashboard

Telemetry dashboard for observing ego-mcp in action.

- **Now tab**: Summary cards + real-time charts + event feed
- **History tab**: Tool usage counts and parameter trends with time range selection
- **Logs tab**: Live tail of masked logs

### Run (Docker Compose)

```bash
cd dashboard
cp .env.example .env
docker compose up --build
```

- Backend: http://localhost:8000
- Frontend: http://localhost:4173

See [dashboard/README.md](dashboard/README.md) for full documentation.

## Development

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Node.js (dashboard frontend)
- Docker + Docker Compose (dashboard)

### Test & Lint

```bash
# ego-mcp
cd ego-mcp
GEMINI_API_KEY=test-key uv run pytest tests -v
uv run ruff check src tests
uv run mypy src tests

# dashboard backend
cd dashboard
uv run pytest -v
uv run ruff check src tests
uv run mypy src tests

# dashboard frontend
cd dashboard/frontend
npm ci
npm run lint
npm run test
npm run build
```

## Acknowledgments

- [embodied-claude](https://github.com/kmizu/embodied-claude) by [@kmizu](https://github.com/kmizu)

## License

MIT
