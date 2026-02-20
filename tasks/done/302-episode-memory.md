# 302: エピソード記憶（Phase 3）

## 目的
複数記憶を束ねるエピソード単位の保存・検索・取得を提供する。

## 前提
- `MemoryStore` が利用可能であること
- ChromaDB を別コレクションで扱えること

## 参照
- `design/tasks.md` の T-302
- `memory-mcp/src/memory_mcp/episode.py`

## タスク
- [ ] 参考実装を基に `src/ego_mcp/episode.py` を整備
- [ ] エピソード用コレクション初期化を実装（例: `ego_episodes`）
- [ ] `create(memory_ids, summary)` を実装
- [ ] `search(query, ...)` を実装
- [ ] `get_by_id(episode_id)` を実装
- [ ] `create_episode` / `get_episode` ツールとの整合を確認

## テスト
- [ ] `tests/test_episode.py` を作成
  - 作成・検索・詳細取得
  - 不正 ID 時の戻り値
- [ ] `tests/test_integration.py` の episode ケースを拡充

## 完了確認
```bash
cd ego-mcp
uv run pytest tests/test_episode.py -v
uv run pytest tests/test_integration.py -k episode -v
```

