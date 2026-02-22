# ego-mcp dashboard (Phase 1-2 backend)

`design/ego-mcp-dashboard-design.md` に基づく Phase 1-2 のサーバー側実装です。

## 実装済み

- `/api/v1/current`（Now タブ初期表示向け）
- `/api/v1/usage/tools`（ツール使用回数）
- `/api/v1/metrics/{key}`（数値メトリクス履歴）
- `/api/v1/metrics/{key}/string-timeline`（string 推移タイムライン）
- `/api/v1/metrics/{key}/heatmap`（string 出現頻度ヒートマップ）
- `/api/v1/alerts/anomalies`（急増/急落アラート）
- private フィールドのマスキング・allow-list フィルタ

## 開発

```bash
cd dashboard
uv sync --group dev
uv run pytest -v
uv run ruff check src tests
uv run mypy src tests
```
