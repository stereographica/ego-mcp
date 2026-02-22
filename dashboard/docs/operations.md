# Operations

- 更新責任者: ego-mcp dashboard maintainers

## 開発者向け

### 監視ポイント（ダッシュボード自身）

- backend health: `GET /api/v1/current` が 200 を返すか
- DB 接続: backend / ingestor のログに `psycopg` 接続失敗が出ていないか
- Redis 接続: `dashboard:current` 更新が継続しているか
- ingestor: `failed to parse jsonl line` 警告の増加有無

### 障害切り分けの順序

1. `docker compose ps`
2. `docker compose logs --tail=200 backend`
3. `docker compose logs --tail=200 ingestor`
4. `docker compose logs --tail=100 db redis`
5. `curl http://localhost:8000/api/v1/current`

## 運用者向け

### バックアップ

- TimescaleDB: `pg_dump` / スナップショット運用を採用
- Redis: `dashboard:current` は再生成可能キャッシュのため優先度低
- 取り込み元 JSONL (`DASHBOARD_LOG_PATH`, glob 対応) はダッシュボード外の主系ログ保全方針に従う

### ログローテーション

- ingestor は inode 変更 / truncate を検知して再追従し、glob 指定時は最新一致ファイルに切替
- ローテーション方式は `copytruncate` より rename + reopen 推奨

### 障害対応（よくある事象）

- 画面は開くが数値が増えない:
  - ingestor が停止している、または `DASHBOARD_LOG_PATH` / `DASHBOARD_LOG_MOUNT_SOURCE` が誤っている
- Logs タブが空:
  - 取り込み元 JSONL に log event が含まれていない
- compose 起動時に frontend から API 接続できない:
  - `.env` の `VITE_DASHBOARD_API_BASE` / `VITE_DASHBOARD_WS_BASE` が `localhost` になっているか確認
