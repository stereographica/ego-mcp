# ego-mcp dashboard (Phase 1-2)

This is the Phase 1-2 implementation based on `design/ego-mcp-dashboard-design.md`.

## Implementation Notes

- Persistence: **TimescaleDB**
- Real-time latest-value cache: **Redis**
- Startup: **docker compose**

When both `DASHBOARD_DATABASE_URL` and `DASHBOARD_REDIS_URL` are set,
`SqlTelemetryStore` is enabled and uses TimescaleDB/Redis.
If either is missing, the app falls back to `TelemetryStore` in memory.

Backend CORS is configured with `DASHBOARD_CORS_ALLOWED_ORIGINS` as a comma-separated list.
Example: `http://localhost:4173,http://127.0.0.1:4173`

## Startup With Docker Compose

```bash
cd dashboard
cp .env.example .env
docker compose up --build
```

- backend: `http://localhost:8000`
- frontend: `http://localhost:4173`
- db (TimescaleDB): `localhost:5432`
- redis: `localhost:6379`
- ingestor: tails `DASHBOARD_LOG_PATH` (file or glob) and writes into DB/Redis
- `ingestion_checkpoints` stores inode/offset per file and resumes from the last position after restart
- `dedupe_key` prevents replayed JSONL rows from being counted twice

`ego-mcp` writes `ego-mcp-YYYY-MM-DD.log` under `EGO_MCP_LOG_DIR` (default: `/tmp`).
The dashboard follows that convention and watches `/host-tmp/ego-mcp-*.log` by default.

Desire rendering uses `${DASHBOARD_EGO_MCP_DATA_DIR}/settings/desires.json` as the source of truth.
The frontend loads fixed desires from `GET /api/v1/desires/catalog` and renders them in `(maslow_level, id)` order.
The catalog API also returns `status` and `errors`, so the backend can report a missing or invalid settings file.
Legacy fixed desires that do not exist in the catalog are hidden from both Now and History.

## backend API

- `/api/v1/current`
- `/api/v1/usage/tools`
- `/api/v1/metrics/{key}`
- `/api/v1/metrics/{key}/string-timeline`
- `/api/v1/metrics/{key}/heatmap`
- `/api/v1/desires/catalog`
- `/api/v1/logs`
- `/api/v1/alerts/anomalies`
- `/api/v1/relationships/overview`
- `/api/v1/relationships/surface-timeline`
- `/api/v1/relationships/{person_id}/detail`

See `dashboard/docs/` for details: `getting-started.md`, `configuration.md`, `operations.md`, and `api.md`.

## Development

Prerequisites:

- Python 3.14
- Node.js 24
- Docker + Docker Compose

### backend

```bash
cd dashboard
uv sync --group dev
uv run pytest -v
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src tests
```

### Maintenance

If you want to remove replay duplicates from existing data and reset checkpoints to the current log tail:

```bash
cd dashboard
uv run python -m ego_dashboard.dedupe_telemetry --log-path "${DASHBOARD_LOG_PATH}"
```

### frontend

```bash
cd dashboard/frontend
npm install
npm run lint
npm run format:check
npm run test
npm run build
```
