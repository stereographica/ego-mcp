# 602: recall フィルタ強化と search_memories 統合

## 目的
`recall` に日付フィルタを追加し、結果表示を改善する。同時に `search_memories` バックエンドツールを廃止して `recall` に統合する。LLM ユーザーから「recall と search_memories の使い分けがわからない」という要望に対応する。

## 前提
- `recall` / `search_memories` が動作していること
- `MemoryStore.search` が `date_from` / `date_to` をサポート済みであること
- 601（相対時間フォーマット関数）が完了していること

## 参照
- `design/phase3-enhancements.md` §5

## タスク

### T-602-1: `recall` ツールスキーマに `date_from` / `date_to` を追加
対象ファイル: `src/ego_mcp/server.py`

`SURFACE_TOOLS` 内の `recall` の `inputSchema.properties` に以下を追加:
```python
"date_from": {"type": "string", "description": "ISO date (YYYY-MM-DD)"},
"date_to": {"type": "string", "description": "ISO date (YYYY-MM-DD)"},
```

### T-602-2: `_handle_recall` に `date_from` / `date_to` を渡す
対象ファイル: `src/ego_mcp/server.py`

`_handle_recall` で `args` から `date_from` / `date_to` を取得し、`memory.search()` に渡す。`has_filters` 判定に `date_from`, `date_to` を含める。

`n_results` に上限キャップ `min(args.get("n_results", 3), 10)` を適用する。

### T-602-3: recall の結果表示を改善
対象ファイル: `src/ego_mcp/server.py`

結果表示を以下の形式に変更する:
```
3 of ~50 memories (showing top matches):
1. [2d ago] Discussed heartbeat config
   emotion: curious | importance: 4 | score: 0.87
```

表示ルール:
- ヘッダに `N of ~M memories` で全体のうちいくつ表示しているか明示
- timestamp は相対時間（601 で実装した `_relative_time` を使用）
- `intensity >= 0.7` の時だけ `emotion: moved(0.9)` と数値表示
- `secondary` 感情があれば先頭 1 件を `undercurrent: anxious` として表示
- `is_private` が true の記憶だけ `private` フラグ表示。false は省略
- content は 70 文字で truncate

全体の記憶件数は `MemoryStore` の collection count から取得する。`_ensure_connected().count()` を呼ぶか、`search`/`recall` の返り値とは別に取得する方法を検討する。

### T-602-4: search_memories を廃止
対象ファイル: `src/ego_mcp/server.py`

- `BACKEND_TOOLS` から `search_memories` の `Tool` 定義を削除
- `_dispatch` から `"search_memories"` のケースを削除
- `_handle_search_memories` 関数を削除

### T-602-5: `SCAFFOLD_RECALL` を動的スキャフォールドに置き換え
対象ファイル: `src/ego_mcp/scaffolds.py`, `src/ego_mcp/server.py`

`scaffolds.py` から固定の `SCAFFOLD_RECALL` を削除し、`server.py` 内に動的スキャフォールド生成関数を実装する。

```python
def _recall_scaffold(n_shown: int, total_count: int, filters_used: list[str]) -> str:
```

ロジック:
- `n_shown < total_count` の場合: `"Showing N of ~M. Increase n_results for more."` を含める
- フィルタ未使用時: 使用可能なフィルタを全て案内
- フィルタ使用時: まだ使っていないフィルタだけ案内
- 常に `"Need narrative detail? Use get_episode."` と `"If you found a new relation, use link_memories."` を含める

## テスト
- [ ] `recall` に `date_from`/`date_to` を渡して期間内の記憶のみ返ることを確認
- [ ] `n_results=10` でキャップが適用されることを確認
- [ ] `search_memories` がツールリストに含まれないことを確認
- [ ] 動的スキャフォールドがフィルタ使用状況に応じて変化することを確認
- [ ] 結果表示に相対時間・undercurrent・total count が含まれることを確認

## 完了確認
```bash
cd ego-mcp
uv run pytest tests/test_integration.py -k "recall" -v
uv run pytest tests/ -v  # search_memories 参照が残っていないことを確認
uv run mypy src/ego_mcp/server.py
uv run mypy src/ego_mcp/scaffolds.py
```
