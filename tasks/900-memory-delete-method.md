# 900: MemoryStore.delete メソッドの追加

## 目的
`MemoryStore` に記憶を削除する `delete` メソッドを追加する。削除時に双方向リンクの整合性を保つため、削除対象の `linked_ids` に含まれる全ターゲットの逆リンクを除去してから ChromaDB エントリを削除する。

## 前提
- `MemoryStore` が動作していること
- `MemoryStore.get_by_id` が動作していること
- `link_memories` による双方向リンクが正しく作成されていること

## 参照
- `design/forget-tool-design.md` §A

## タスク

### T-900-1: `MemoryStore.delete` メソッドの実装
対象ファイル: `ego-mcp/src/ego_mcp/memory.py`

`MemoryStore` クラスに以下のシグネチャのメソッドを追加する:

```python
async def delete(self, memory_id: str) -> Memory | None:
```

返り値は削除された `Memory`（確認表示用）。ID が見つからない場合は `None` を返す。

**処理の流れ:**
1. `get_by_id(memory_id)` で削除対象の記憶を取得する。`None` の場合はそのまま `None` を返す
2. 削除対象の `linked_ids` を走査し、各リンク先の記憶から逆リンク（`target_id == memory_id` の `MemoryLink`）を除去する:
   - `get_by_id(link.target_id)` でリンク先記憶を取得
   - リンク先が `None`（既に削除済み）の場合はスキップ
   - リンク先の `linked_ids` から `target_id == memory_id` のエントリをフィルタして除外
   - `collection.update()` でリンク先のメタデータを更新（`_links_to_json` を使用）
3. `collection.delete(ids=[memory_id])` で ChromaDB からエントリを削除する
4. Step 1 で取得した `Memory` オブジェクトを返す

逆リンクの除去（Step 2）を先に行い、ChromaDB 削除（Step 3）を後に行う順序とする。

### T-900-2: テスト
対象ファイル: `ego-mcp/tests/test_memory.py`

以下のテストケースを追加する:

- リンクなしの記憶を削除した場合: 返り値が `Memory` であること、`get_by_id` で `None` が返ること
- 双方向リンクのある記憶を削除した場合: リンク先記憶の `linked_ids` から逆リンクが除去されていること
- 存在しない ID を削除した場合: `None` が返ること
- 削除後に `collection_count` が 1 減少していること

## 完了確認
```bash
cd ego-mcp
GEMINI_API_KEY=test-key uv run pytest tests/test_memory.py -k "delete" -v
uv run mypy src/ego_mcp/memory.py
```
