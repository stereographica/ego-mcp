# Suggested Commands

## ego-mcp

### Setup
```bash
cd ego-mcp
uv sync --dev          # or: uv sync --extra dev
```

### Run / Verify
```bash
cd ego-mcp
uv run python -c "import ego_mcp; print(ego_mcp.__version__)"
uv run python -m ego_mcp
```

### Tests / Lint / Type Check
```bash
cd ego-mcp
GEMINI_API_KEY=test-key uv run pytest tests -v
uv run isort --check-only src tests
uv run ruff check src tests
uv run mypy src tests
```

### Environment Variables
```bash
export GEMINI_API_KEY="..."
# or
export EGO_MCP_EMBEDDING_PROVIDER="openai"
export OPENAI_API_KEY="..."
export EGO_MCP_DATA_DIR="$HOME/.ego-mcp/data"
export EGO_MCP_COMPANION_NAME="Master"
```

## dashboard backend

### Setup
```bash
cd dashboard
uv sync --group dev
```

### Tests / Lint / Format / Type Check
```bash
cd dashboard
uv run pytest -v
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src tests
```

## dashboard frontend

### Setup
```bash
cd dashboard/frontend
npm ci
```

### Lint / Format / Test / Build
```bash
cd dashboard/frontend
npm run lint
npm run format:check
npm run test
npm run build
```

### Dev server
```bash
cd dashboard/frontend
npm run dev
```

## docker-compose
```bash
cd dashboard
docker compose config   # validate
docker compose up -d    # run
```

## General (Darwin/macOS)
```bash
git status
git diff
rg "<pattern>" ego-mcp   # fast text search
```