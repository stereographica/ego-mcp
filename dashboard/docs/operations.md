# Operations

- Maintainer: ego-mcp dashboard maintainers

## For Developers

### Monitoring Checklist

- Backend health: confirm `GET /api/v1/current` returns HTTP 200.
- Database connectivity: confirm backend and ingestor logs do not show `psycopg` connection failures.
- Redis connectivity: confirm `dashboard:current` continues to update.
- Ingestor: watch for increases in `failed to parse jsonl line` warnings.

### Incident Triage Order

1. `docker compose ps`
2. `docker compose logs --tail=200 backend`
3. `docker compose logs --tail=200 ingestor`
4. `docker compose logs --tail=100 db redis`
5. `curl http://localhost:8000/api/v1/current`

## For Operators

### Backups

- TimescaleDB: use `pg_dump` or your snapshot-based backup workflow.
- Redis: `dashboard:current` is a rebuildable cache, so it has lower backup priority.
- Source JSONL logs (`DASHBOARD_LOG_PATH`, including glob patterns) should follow the primary log retention policy outside the dashboard.

### Log Rotation

- The ingestor detects inode changes and truncation, resumes tailing automatically, and keeps checkpoints per file when glob patterns are used.
- Prefer `rename + reopen` over `copytruncate` for log rotation.

### Common Operational Issues

- The dashboard loads, but metrics do not increase:
  The ingestor may be stopped, or `DASHBOARD_LOG_PATH` / `DASHBOARD_LOG_MOUNT_SOURCE` may be incorrect.
- Tool calls spike after restarting the ingestor:
  Run `uv run python -m ego_dashboard.dedupe_telemetry --log-path "$DASHBOARD_LOG_PATH"` to remove replay duplicates and reset checkpoints to the current EOF.
- The Logs tab is empty:
  The source JSONL stream does not include log events.
- The frontend cannot reach the API after `docker compose up`:
  Confirm `.env` sets `VITE_DASHBOARD_API_BASE` and `VITE_DASHBOARD_WS_BASE` to `localhost`.
