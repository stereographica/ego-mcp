# API

- Maintainer: ego-mcp dashboard maintainers

## For Developers

### REST (History / Current)

- `GET /api/v1/current`
  - Current summary values (`latest`, `tool_calls_per_min`, `error_rate`)
- `GET /api/v1/usage/tools?from=...&to=...&bucket=1m|5m|15m`
  - Tool usage series. Counts `Tool invocation` logs as one call each, and only falls back to terminal events for older data without logs
- `GET /api/v1/metrics/{key}?from=...&to=...&bucket=...`
  - Averaged numeric metric series
- `GET /api/v1/metrics/{key}/string-timeline?from=...&to=...`
  - Timeline points for a string metric
- `GET /api/v1/metrics/{key}/heatmap?from=...&to=...&bucket=...`
  - Frequency distribution of string values
- `GET /api/v1/desires/catalog`
  - Fixed desire catalog. The response shape is `{ version, status, errors, source_path, fixed_desires, implicit_rules, emergent }`
  - `fixed_desires` is `[{ id, display_name, satisfaction_hours, maslow_level }]`
  - `status` is `ok | missing | invalid | unconfigured`
  - The frontend uses this catalog as the source of truth for fixed desire labels and ordering
- `GET /api/v1/desires/keys?from=...&to=...`
  - Desire keys seen during the selected history range, used for dynamic series discovery in the history chart
  - Returns only fixed desires that exist in the catalog and dynamic desires that do not
  - Legacy fixed desires that are not in the catalog are excluded
- `GET /api/v1/logs?from=...&to=...&level=INFO&search=remember`
  - Logs for live tail and history views (up to 300 rows)
- `GET /api/v1/alerts/anomalies?from=...&to=...&bucket=...`
  - Usage/intensity spike detection
- `GET /api/v1/memory/network`
  - Memory network graph (nodes: memories + notions, edges: links + `notion_source`)
  - Response shape: `{ nodes: [{id, label, category, decay, access_count, is_notion}], edges: [{source, target, link_type, confidence}] }`
  - Reads ego-mcp ChromaDB + `notions.json` directly, using `DASHBOARD_EGO_MCP_DATA_DIR`
- `GET /api/v1/notions`
  - Notion list: `label`, `emotion_tone`, `confidence`, `source_count`, `created`, `last_reinforced`
- `GET /api/v1/notions/{notion_id}/history?from=...&to=...&bucket=15m`
  - Confidence history for a specific notion, preferring notion-level confidence maps when aggregating telemetry events

### WebSocket (Current View)

- `WS /ws/current`
- Outgoing events:
  - `current_snapshot`: current-value snapshot
  - `log_line`: latest log line when available
  - `ping`: keepalive

### Example (REST)

```bash
curl "http://localhost:8000/api/v1/usage/tools?from=2026-01-01T00:00:00Z&to=2026-01-01T01:00:00Z&bucket=5m"
```

## For Operators

### Authorization

- The current implementation does not include API/WS authorization and assumes local or internal-network usage
- For public deployment, enforce authentication/authorization at the reverse proxy layer (Basic auth, OIDC, IP restrictions, and so on)

### Rate Limiting

- The application currently has no built-in rate limiting
- Recommended:
  - REST: burst limits per IP
  - WS: concurrent connection limits plus an idle timeout

### Compatibility Notes

- If `bucket` is set to an unsupported value, the implementation falls back to a default bucket (`1m` or `5m`)
