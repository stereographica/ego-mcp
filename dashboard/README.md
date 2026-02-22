# ego-mcp dashboard (Phase 1-2)

`design/ego-mcp-dashboard-design.md` に基づく Phase 1-2 実装です。

## 実装方針（重要）

- 永続化: **TimescaleDB**
- リアルタイム最新値キャッシュ: **Redis**
- 起動: **docker-compose**

`DASHBOARD_DATABASE_URL` と `DASHBOARD_REDIS_URL` が設定されると、
`SqlTelemetryStore` が有効化され、TimescaleDB/Redis を利用します。
未設定時は `TelemetryStore`（in-memory）へフォールバックします。

## 起動（docker-compose）

```bash
cd dashboard
cp .env.example .env
docker compose up --build
```

- backend: `http://localhost:8000`
- frontend: `http://localhost:4173`
- db (TimescaleDB): `localhost:5432`
- redis: `localhost:6379`
- ingestor: `DASHBOARD_LOG_PATH` を tail して DB/Redis に反映

## backend API

- `/api/v1/current`
- `/api/v1/usage/tools`
- `/api/v1/metrics/{key}`
- `/api/v1/metrics/{key}/string-timeline`
- `/api/v1/metrics/{key}/heatmap`
- `/api/v1/logs`
- `/api/v1/alerts/anomalies`

詳細は `dashboard/docs/` 配下（`getting-started.md`, `configuration.md`, `operations.md`, `api.md`）を参照してください。

## 開発

### backend

```bash
cd dashboard
uv sync --group dev
uv run pytest -v
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src tests
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
