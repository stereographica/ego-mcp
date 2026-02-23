# Project Overview

This monorepo (`nyamco-ego`) contains two main subprojects plus supporting directories.

## Repository Layout

```
nyamco-ego/
├── ego-mcp/          # Primary MCP server (Python)
├── dashboard/        # Telemetry dashboard (FastAPI backend + React frontend)
│   ├── src/          #   Backend (ego_dashboard)
│   └── frontend/     #   Frontend (React + Vite + TypeScript)
├── embodied-claude/  # Embodied Claude project (separate git repo)
├── design/           # Design documents
└── .github/workflows/ego-mcp-ci.yml  # CI (4 jobs)
```

## ego-mcp

MCP server providing cognitive scaffolding tools for AI personality continuity.

- Package: `ego-mcp/src/ego_mcp`
- Entrypoint: `python -m ego_mcp`

### Tech Stack

- Python >=3.11, pinned locally to 3.14 via `.python-version`
- Build: Hatchling
- Environment/deps: `uv`
- MCP SDK: `mcp>=1.0.0`
- Vector/memory: `chromadb`
- HTTP: `httpx`
- System info: `psutil`
- Math: `numpy`
- Validation: `pydantic >=2.12,<2.13`
- Testing: `pytest`, `pytest-asyncio`, `respx`
- Linting: `ruff` (line-length=88, target py311)
- Type checking: `mypy` strict mode

### Source Modules (`ego-mcp/src/ego_mcp/`)

| Module              | Purpose                                  |
|---------------------|------------------------------------------|
| `server.py`         | MCP server, tool registration & handlers |
| `config.py`         | Config from env vars (frozen dataclass)  |
| `memory.py`         | Memory storage/retrieval                 |
| `desire.py`         | Desire state/engine                      |
| `embedding.py`      | Embedding provider abstraction           |
| `scaffolds.py`      | Response scaffolding templates           |
| `types.py`          | Core dataclasses/enums                   |
| `hopfield.py`       | Hopfield network pattern store           |
| `relationship.py`   | Relationship tracking                    |
| `episode.py`        | Episodic memory                          |
| `consolidation.py`  | Memory consolidation                     |
| `association.py`    | Associative memory                       |
| `self_model.py`     | Self-model representation                |
| `interoception.py`  | Internal state sensing                   |
| `workspace_sync.py` | Workspace synchronization                |
| `local_chromadb.py` | Local ChromaDB implementation            |
| `chromadb_compat.py`| ChromaDB compatibility layer             |
| `logging_utils.py`  | Logging utilities                        |

### Configuration

- Default embedding provider: `gemini` (needs `GEMINI_API_KEY`)
- Alternative: `openai` (set `EGO_MCP_EMBEDDING_PROVIDER=openai`, needs `OPENAI_API_KEY`)
- Data dir: `~/.ego-mcp/data` (configurable via `EGO_MCP_DATA_DIR`)
- Companion name: configurable via `EGO_MCP_COMPANION_NAME`

## dashboard

Telemetry dashboard for ego-mcp.

- Backend package: `dashboard/src/ego_dashboard`
- Frontend: `dashboard/frontend/`

### Backend Tech Stack

- Python >=3.11
- FastAPI + Uvicorn
- PostgreSQL (psycopg)
- Redis
- Pydantic >=2.11
- Testing: pytest
- Linting: ruff (line-length=100, select E/F/I/UP)
- Type checking: mypy strict
- Build: Hatchling

### Backend Modules (`dashboard/src/ego_dashboard/`)

| Module         | Purpose                       |
|----------------|-------------------------------|
| `api.py`       | FastAPI routes                |
| `models.py`    | Data models                   |
| `store.py`     | Data store abstraction        |
| `sql_store.py` | PostgreSQL store impl         |
| `ingestor.py`  | Data ingestion                |
| `settings.py`  | App settings                  |
| `constants.py` | Constants                     |

### Frontend Tech Stack

- React 19, TypeScript ~5.9
- Vite 7, Vitest
- Tailwind (via tailwind-merge + clsx)
- Recharts (charting)
- Radix UI (tabs)
- Lucide React (icons)
- ESLint + Prettier

## CI (`.github/workflows/ego-mcp-ci.yml`)

4 jobs triggered on PRs/push to main:
1. `ego-mcp-test-lint-typecheck` — pytest + ruff + mypy
2. `dashboard-test-lint-format-typecheck` — pytest + ruff + ruff format + mypy
3. `dashboard-frontend-lint-format-test-build` — eslint + prettier + vitest + tsc+vite build
4. `dashboard-docker-compose-validate` — `docker compose config`