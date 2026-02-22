# Configuration

- 更新責任者: ego-mcp dashboard maintainers

## 開発者向け

### 環境変数一覧

| 変数名 | 既定値 | 用途 |
| --- | --- | --- |
| `DASHBOARD_DATABASE_URL` | なし | TimescaleDB 接続先。backend/ingestor 共通 |
| `DASHBOARD_REDIS_URL` | なし | Redis 接続先。backend/ingestor 共通 |
| `DASHBOARD_CORS_ALLOWED_ORIGINS` | `http://localhost:4173,http://127.0.0.1:4173,http://localhost:5173,http://127.0.0.1:5173` | backend API の CORS allow origins（カンマ区切り） |
| `DASHBOARD_LOG_MOUNT_SOURCE` | `/tmp` | (compose) ホスト側ログディレクトリ |
| `DASHBOARD_LOG_MOUNT_TARGET` | `/host-tmp` | (compose) ingestor コンテナ側 mount 先 |
| `DASHBOARD_LOG_PATH` | `/tmp/ego-mcp-*.log` (ローカル) / `/host-tmp/ego-mcp-*.log` (compose) | ingestor が tail する JSONL ログファイル / glob |
| `DASHBOARD_INGEST_POLL_SECONDS` | `1.0` | ingestor のファイルポーリング間隔（秒） |
| `VITE_DASHBOARD_API_BASE` | `http://localhost:8000` | ブラウザから参照する API URL |
| `VITE_DASHBOARD_WS_BASE` | `ws://localhost:8000` | ブラウザから参照する WS URL |

### ストア切替条件

- `DASHBOARD_DATABASE_URL` と `DASHBOARD_REDIS_URL` の両方が設定されると `SqlTelemetryStore` を使用
- どちらか欠ける場合は `TelemetryStore`（in-memory）へフォールバック

### CORS 設定（AllowedOrigin）

- backend API は `DASHBOARD_CORS_ALLOWED_ORIGINS` をカンマ区切りで解釈する
- docker-compose の既定値は `http://localhost:4173,http://127.0.0.1:4173`
- Vite をローカル単体起動する場合（既定 `5173`）は、必要に応じて `5173` を追加する
- 例:
  - `DASHBOARD_CORS_ALLOWED_ORIGINS=http://localhost:4173,http://127.0.0.1:4173`
  - `DASHBOARD_CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173`

### ログパス設定（ego-mcp 仕様との整合）

- `ego-mcp` のログ出力先は `EGO_MCP_LOG_DIR`（既定 `/tmp`）で変更可能
- `ego-mcp` は `ego-mcp-YYYY-MM-DD.log` 形式の日付付き JSONL ログを出力
- `dashboard` の `DASHBOARD_LOG_PATH` は単一ファイルだけでなく glob も受け付ける
- compose ではホストの `DASHBOARD_LOG_MOUNT_SOURCE`（既定 `/tmp`）をコンテナに read-only mount
- ingestor は inode 変更 / truncate と、glob の最新一致ファイルへの切替（日次ローテーション相当）に対応

## 運用者向け

### private マスキング設定

- 収集時:
  - `private=true` のイベント/ログは `message` を `REDACTED` に変換
  - event の string params は allow-list (`time_phase`, `emotion_primary`, `mode`, `state`) のみ保持
- 配信時:
  - `/api/v1/logs` は `private=true` の行を再度 `REDACTED` 化（防御的マスク）
  - `/api/v1/current` も `private=true` の `latest.message` を再マスク

### 推奨設定値（本番/常設）

- `DASHBOARD_LOG_MOUNT_SOURCE=/tmp`（compose）
- `DASHBOARD_LOG_PATH=/host-tmp/ego-mcp-*.log`（compose）
- `DASHBOARD_INGEST_POLL_SECONDS=1.0`（通常）
- 高負荷時は `1.5-2.0` 秒へ調整
