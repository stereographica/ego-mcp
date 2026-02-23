# CLAUDE.md

This monorepo contains **ego-mcp** (MCP server) and **dashboard** (telemetry UI).

## Repository Layout

```
nyamco-ego/
├── ego-mcp/          # Primary MCP server (Python)
├── dashboard/        # Telemetry dashboard
│   ├── src/          #   Backend (FastAPI + PostgreSQL + Redis)
│   └── frontend/     #   Frontend (React + Vite + TypeScript)
├── embodied-claude/  # Embodied Claude project (separate git repo, submodule)
├── design/           # Design documents
└── .github/workflows/ego-mcp-ci.yml  # CI for ego-mcp + dashboard
```

## ego-mcp

- Python package: `ego-mcp/src/ego_mcp`
- Runtime entrypoint: `python -m ego_mcp`

### Setup

```bash
cd ego-mcp
uv sync --extra dev
```

Required environment variables (choose one embedding provider):

```bash
export GEMINI_API_KEY="your-gemini-api-key"
# or
export EGO_MCP_EMBEDDING_PROVIDER="openai"
export OPENAI_API_KEY="your-openai-api-key"
```

### Verify

```bash
cd ego-mcp
uv run python -c "import ego_mcp; print(ego_mcp.__version__)"
uv run python -m ego_mcp
```

### Tool Usage Flow (Minimal)

- Session start: `wake_up` -> `introspect` -> save reflection with `remember`
- Heartbeat: `feel_desires` -> if needed `introspect` -> act or `HEARTBEAT_OK`
- Before important responses: `consider_them` -> `am_i_being_genuine`
- After significant experiences: `remember`

## dashboard

- Backend package: `dashboard/src/ego_dashboard`
- Frontend: `dashboard/frontend/` (React + Vite + TypeScript)

### Setup

```bash
# Backend
cd dashboard
uv sync --group dev

# Frontend
cd dashboard/frontend
npm ci
```

## Development Commands

### ego-mcp

```bash
cd ego-mcp
GEMINI_API_KEY=test-key uv run pytest tests -v
uv run isort --check-only src tests
uv run ruff check src tests
uv run mypy src tests
```

### dashboard backend

```bash
cd dashboard
uv run pytest -v
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src tests
```

### dashboard frontend

```bash
cd dashboard/frontend
npm run lint
npm run format:check
npm run test
npm run build
```

## Mandatory CI Gate After Code Changes

If any code under `ego-mcp/` or `dashboard/` is changed, run the
corresponding checks defined in `.github/workflows/ego-mcp-ci.yml`
before finishing work.

### ego-mcp CI sequence

```bash
cd ego-mcp
uv sync --extra dev
GEMINI_API_KEY=test-key uv run pytest tests -v
uv run isort --check-only src tests
uv run ruff check src tests
uv run mypy src tests
```

### dashboard backend CI sequence

```bash
cd dashboard
uv sync --group dev
uv run pytest -v
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src tests
```

### dashboard frontend CI sequence

```bash
cd dashboard/frontend
npm ci
npm run lint
npm run format:check
npm run test
npm run build
```

### dashboard docker-compose validation

```bash
cd dashboard
docker compose config
```

Rule:
- Do not conclude the task while any check is failing.
- Fix issues and rerun the failed checks until all required checks pass.

## Troubleshooting: `hashlib blake2*` with `uv`

If `uv` shows `unsupported hash type blake2b/blake2s`, a broken Python (often `pyenv`) is being selected.

```bash
cd ego-mcp
rm -rf .venv
uv sync --dev
```

This repo pins Python via `ego-mcp/.python-version` (`3.14`).
CI uses Python `3.11` (the minimum supported version).
If needed, run once with an explicit interpreter:

```bash
uv run --python /opt/homebrew/bin/python3.14 python -c "import hashlib; print(hasattr(hashlib, 'blake2b'))"
```
