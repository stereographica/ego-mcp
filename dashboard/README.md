# ego-mcp dashboard (Phase 1-2)

`design/ego-mcp-dashboard-design.md` に基づく Phase 1-2 の実装です。

## backend 実装済み

- `/api/v1/current`（Now タブ初期表示向け）
- `/api/v1/usage/tools`（ツール使用回数）
- `/api/v1/metrics/{key}`（数値メトリクス履歴）
- `/api/v1/metrics/{key}/string-timeline`（string 推移タイムライン）
- `/api/v1/metrics/{key}/heatmap`（string 出現頻度ヒートマップ）
- `/api/v1/alerts/anomalies`（急増/急落アラート）
- private フィールドのマスキング・allow-list フィルタ

## frontend 実装済み

- `frontend/` に Now / History / Logs タブを実装
- Now: cards + intensity 折れ線 + event feed
- History: tool usage stacked area + string heatmap 表示
- Logs: live-tail 風表示（private 想定文字列の REDACTED 表示）
- 2秒ポーリング更新

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
