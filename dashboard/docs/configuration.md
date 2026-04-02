# Configuration

- Maintainer: ego-mcp dashboard maintainers

## For Developers

### Environment Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `DASHBOARD_DATABASE_URL` | none | TimescaleDB connection URL shared by backend and ingestor |
| `DASHBOARD_REDIS_URL` | none | Redis connection URL shared by backend and ingestor |
| `DASHBOARD_CORS_ALLOWED_ORIGINS` | `http://localhost:4173,http://127.0.0.1:4173,http://localhost:5173,http://127.0.0.1:5173` | Backend API CORS allow-origins, comma-separated |
| `DASHBOARD_LOG_MOUNT_SOURCE` | `/tmp` | Host log directory for compose |
| `DASHBOARD_LOG_MOUNT_TARGET` | `/host-tmp` | Ingestor-side mount target for compose |
| `DASHBOARD_LOG_PATH` | `/tmp/ego-mcp-*.log` (local) / `/host-tmp/ego-mcp-*.log` (compose) | JSONL log file or glob tailed by the ingestor |
| `DASHBOARD_INGEST_POLL_SECONDS` | `1.0` | Ingestor file polling interval in seconds |
| `DASHBOARD_EGO_MCP_DATA_DIR` | none | ego-mcp data directory. Used by the Memory Network / Notions API to read ChromaDB and `notions.json`, and by the desire catalog loader to read `settings/desires.json`. In compose, the same absolute path is mounted into the backend container with write access because Chroma may touch SQLite state even during reads |
| `VITE_DASHBOARD_API_BASE` | `http://localhost:8000` | API base URL used by the browser |
| `VITE_DASHBOARD_WS_BASE` | `ws://localhost:8000` | WebSocket base URL used by the browser |

### Store Selection

- If both `DASHBOARD_DATABASE_URL` and `DASHBOARD_REDIS_URL` are set, the app uses `SqlTelemetryStore`
- If either is missing, it falls back to `TelemetryStore` in memory
- `SqlTelemetryStore` keeps `dedupe_key` in `tool_events` and `log_events` and ignores duplicate `(ts, dedupe_key)` inserts
- Resume offsets are stored in the `ingestion_checkpoints` table

### CORS Settings

- The backend parses `DASHBOARD_CORS_ALLOWED_ORIGINS` as a comma-separated list
- The default docker-compose value is `http://localhost:4173,http://127.0.0.1:4173`
- If you run Vite locally on its default `5173` port, add the `5173` origins as needed
- Examples:
  - `DASHBOARD_CORS_ALLOWED_ORIGINS=http://localhost:4173,http://127.0.0.1:4173`
  - `DASHBOARD_CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173`

### Log Path Settings

- `ego-mcp` log output can be moved with `EGO_MCP_LOG_DIR` (default: `/tmp`)
- `ego-mcp` writes date-stamped JSONL logs in the `ego-mcp-YYYY-MM-DD.log` format
- `dashboard` accepts both a single file path and a glob in `DASHBOARD_LOG_PATH`
- In compose, the host `DASHBOARD_LOG_MOUNT_SOURCE` (default: `/tmp`) is mounted read-only into the container
- The ingestor handles inode changes, truncation, and per-file checkpoints for all files matched by the glob
- On restart, if the inode/offset in `ingestion_checkpoints` still matches a file, ingest resumes from that offset; otherwise it rereads from the beginning
- If `DASHBOARD_EGO_MCP_DATA_DIR` is set, compose mounts that same absolute path into the backend container with write access because Chroma may require SQLite writes during reads

### Desire Catalog Settings

- The dashboard frontend uses `GET /api/v1/desires/catalog` as the source of truth for fixed desires
- The backend reads `DASHBOARD_EGO_MCP_DATA_DIR/settings/desires.json` directly
- The catalog API response includes `version`, `status`, `errors`, `source_path`, `fixed_desires`, `implicit_rules`, and `emergent`
- The frontend uses `display_name` for labels and `(maslow_level, id)` for ordering
- Legacy fixed desires that do not exist in `settings/desires.json` are hidden in the frontend
- If `status=missing` or `status=invalid`, fixed desires are treated as an empty list

## For Operators

### Private Data Masking

- During ingestion:
  - Events/logs with `private=true` have `message` rewritten to `REDACTED`
  - String params in events keep only the allow-list: `time_phase`, `emotion_primary`, `mode`, `state`
- During delivery:
  - `/api/v1/logs` defensively re-masks `private=true` rows as `REDACTED`
  - `/api/v1/current` also re-masks `latest.message` when `private=true`

### Recommended Persistent Settings

- `DASHBOARD_LOG_MOUNT_SOURCE=/tmp` for compose
- `DASHBOARD_LOG_PATH=/host-tmp/ego-mcp-*.log` for compose
- `DASHBOARD_INGEST_POLL_SECONDS=1.0` for normal operation
- Under heavier load, consider increasing it to `1.5-2.0`
- For cleanup/reconciliation: `uv run python -m ego_dashboard.dedupe_telemetry --log-path "$DASHBOARD_LOG_PATH"`
