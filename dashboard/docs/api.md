# API

- 更新責任者: ego-mcp dashboard maintainers

## 開発者向け

### REST（履歴/現在）

- `GET /api/v1/current`
  - 現在値サマリ（latest / tool_calls_per_min / error_rate）
- `GET /api/v1/usage/tools?from=...&to=...&bucket=1m|5m|15m`
  - ツール別使用回数系列
- `GET /api/v1/metrics/{key}?from=...&to=...&bucket=...`
  - 数値メトリクス平均系列
- `GET /api/v1/metrics/{key}/string-timeline?from=...&to=...`
  - string メトリクスの時系列点列
- `GET /api/v1/metrics/{key}/heatmap?from=...&to=...&bucket=...`
  - string 値ごとの出現頻度
- `GET /api/v1/logs?from=...&to=...&level=INFO&logger=name`
  - live tail / 履歴表示用ログ（最大 300 行）
- `GET /api/v1/alerts/anomalies?from=...&to=...&bucket=...`
  - usage/intensity 急増検知

### WebSocket（現在フォーカス）

- `WS /ws/current`
- 送信イベント:
  - `current_snapshot`: 現在値スナップショット
  - `log_line`: 直近ログ（存在時）
  - `ping`: keepalive

### 例（REST）

```bash
curl "http://localhost:8000/api/v1/usage/tools?from=2026-01-01T00:00:00Z&to=2026-01-01T01:00:00Z&bucket=5m"
```

## 運用者向け

### 認可

- 現在の実装では API/WS 認可は未実装（ローカル/内部ネットワーク想定）
- 本番公開時は reverse proxy 側で認証/認可を必須化する（Basic/OIDC/IP 制限など）

### レート制限

- 現在の実装ではアプリ内レート制限は未実装
- 推奨:
  - REST: IP 単位で burst 制限
  - WS: 同時接続数制限 + idle timeout

### 互換性メモ

- `bucket` は未対応値を指定した場合、既定バケット（`1m` または `5m`）へフォールバックする実装あり
