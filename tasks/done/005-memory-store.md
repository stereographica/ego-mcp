# 005: 記憶ストア（MemoryStore）

## 目的
ChromaDB を使った記憶の保存・検索・想起の中核モジュール。

## 前提
- 003（Embedding）、004（types）完了済み

## 参照
- 参考実装: `embodied-claude/memory-mcp/src/memory_mcp/memory.py`
  - スコアリング関数（time_decay, emotion_boost, importance_boost, final_score）を移植
- `design/tool-design.md` の `remember`, `recall` ツール仕様

## 仕様

`src/ego_mcp/memory.py` に `MemoryStore` クラス:

```python
class MemoryStore:
    def __init__(self, config: EgoConfig, embedding_fn: EgoEmbeddingFunction): ...
    async def save(self, content, emotion, importance, category, ...) -> Memory: ...
    async def save_with_auto_link(self, ...) -> tuple[Memory, int]: ...  # returns (memory, num_links)
    async def search(self, query, n_results, emotion_filter, category_filter, ...) -> list[MemorySearchResult]: ...
    async def recall(self, context, n_results) -> list[MemorySearchResult]: ...  # semantic + Hopfield hybrid
    async def list_recent(self, n) -> list[Memory]: ...
    async def get_by_id(self, id) -> Memory | None: ...
```

- `save_with_auto_link`: 保存後に類似メモリ検索（distance < 0.3）→ 双方向リンク
- `recall`: セマンティック検索 + Hopfield パターン補完のハイブリッド。Hopfield は `embodied-claude/memory-mcp/src/memory_mcp/hopfield.py` を移植

## テスト
- save → search で見つかる
- save_with_auto_link で類似メモリにリンクが張られる
- recall がセマンティック + Hopfield 両方の結果を統合して返す
- list_recent が timestamp 降順
- emotion_filter / category_filter が動作

## 完了確認
```bash
pytest tests/test_memory.py -v  # 全 pass
```
