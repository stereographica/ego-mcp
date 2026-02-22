# Configuration

- 更新責任者: ego-mcp dashboard maintainers

## 開発者向け

### 環境変数一覧

| 変数名 | 既定値 | 用途 |
| --- | --- | --- |
| `DASHBOARD_DATABASE_URL` | なし | TimescaleDB 接続先。backend/ingestor 共通 |
| `DASHBOARD_REDIS_URL` | なし | Redis 接続先。backend/ingestor 共通 |
| `DASHBOARD_LOG_PATH` | `/tmp/ego-mcp/telemetry.jsonl` | ingestor が tail する JSONL ログファイル |
| `DASHBOARD_INGEST_POLL_SECONDS` | `1.0` | ingestor のファイルポーリング間隔（秒） |
| `VITE_DASHBOARD_API_BASE` | `http://localhost:8000` | ブラウザから参照する API URL |
| `VITE_DASHBOARD_WS_BASE` | `ws://localhost:8000` | ブラウザから参照する WS URL |

### ストア切替条件

- `DASHBOARD_DATABASE_URL` と `DASHBOARD_REDIS_URL` の両方が設定されると `SqlTelemetryStore` を使用
- どちらか欠ける場合は `TelemetryStore`（in-memory）へフォールバック

### ログパス設定

- compose では `./var/log/ego-mcp` を ingestor コンテナの `/var/log/ego-mcp` に read-only mount
- ログローテーション時は inode 変化または truncate を検知して先頭から再追従

## 運用者向け

### private マスキング設定

- 収集時:
  - `private=true` のイベント/ログは `message` を `REDACTED` に変換
  - event の string params は allow-list (`time_phase`, `emotion_primary`, `mode`, `state`) のみ保持
- 配信時:
  - `/api/v1/logs` は `private=true` の行を再度 `REDACTED` 化（防御的マスク）
  - `/api/v1/current` も `private=true` の `latest.message` を再マスク

### 推奨設定値（本番/常設）

- `DASHBOARD_LOG_PATH=/var/log/ego-mcp/telemetry.jsonl`
- `DASHBOARD_INGEST_POLL_SECONDS=1.0`（通常）
- 高負荷時は `1.5-2.0` 秒へ調整
