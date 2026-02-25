# 902: forget ツールの追加

## 目的
`memory_id` を指定して記憶を削除する `forget` ツールをサーバーに追加する。削除成功時は記憶のサマリを返し、Workspace Sync が有効な場合は同期済みファイルからもエントリを除去する。

## 前提
- 900（`MemoryStore.delete`）が完了していること
- 901（`WorkspaceMemorySync.remove_memory`）が完了していること

## 参照
- `design/forget-tool-design.md` §D

## タスク

### T-902-1: ツール定義の追加
対象ファイル: `ego-mcp/src/ego_mcp/server.py`

`BACKEND_TOOLS` リストに `forget` ツールを追加する。

inputSchema:
```json
{
  "type": "object",
  "properties": {
    "memory_id": {
      "type": "string",
      "description": "ID of the memory to delete"
    }
  },
  "required": ["memory_id"]
}
```

description: `"Delete a memory by ID. Returns the deleted memory's summary for confirmation."`

### T-902-2: `_handle_forget` ハンドラの実装
対象ファイル: `ego-mcp/src/ego_mcp/server.py`

以下のシグネチャのハンドラを追加する:

```python
async def _handle_forget(memory: MemoryStore, args: dict[str, Any]) -> str:
```

**処理の流れ:**
1. `args["memory_id"]` を取得
2. `memory.delete(memory_id)` を呼び出す
3. 返り値が `None` の場合（記憶が見つからない）:
   - data: `"Memory not found: {memory_id}"`
   - scaffold: `"Double-check the ID. Use recall to search for the memory you're looking for."`
4. 削除成功の場合:
   - Workspace Sync が有効かつ `is_private` でなければ `sync.remove_memory(memory_id)` を呼ぶ（`OSError` は catch してログ警告のみ）
   - data: 削除された記憶の相対時間、content（120 文字 truncate）、emotion、importance を含むサマリ
   - scaffold: `"This memory is gone. Was there anything worth preserving in a new form?\nIf this was part of a merge, save the consolidated version with remember."`
5. `compose_response(data, scaffold)` で返す

`_relative_time` と `_truncate_for_quote` は既存のヘルパーを使用する。

### T-902-3: `_dispatch` への分岐追加
対象ファイル: `ego-mcp/src/ego_mcp/server.py`

`_dispatch` 関数に `forget` の分岐を追加する。`satisfy_implicit` は呼ばない（記憶の削除は認知活動ではないため）。

### T-902-4: `_handle_get_episode` の memory_ids フィルタ
対象ファイル: `ego-mcp/src/ego_mcp/server.py`

`_handle_get_episode` で `episode.memory_ids` を返す前に、`memory.get_by_id()` で各 ID の存在を確認し、存在しない ID をフィルタする。削除された記憶があった場合はレスポンスに注記を追加する:

```
Note: {N} memory(ies) no longer exist.
```

### T-902-5: テスト
対象ファイル: `ego-mcp/tests/test_server.py`

以下のテストケースを追加する:

- 存在する記憶 ID で `forget` を呼んだ場合: レスポンスに `"Forgot"` と記憶のサマリが含まれること
- 存在しない記憶 ID で `forget` を呼んだ場合: レスポンスに `"Memory not found"` が含まれること
- `forget` 実行後に `satisfy_implicit` が呼ばれていないこと

## 完了確認
```bash
cd ego-mcp
GEMINI_API_KEY=test-key uv run pytest tests/test_server.py -k "forget" -v
uv run mypy src/ego_mcp/server.py
```
