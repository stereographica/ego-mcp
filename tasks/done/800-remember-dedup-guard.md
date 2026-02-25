# 800: remember 保存前の重複検出ガード

## 目的
`remember` 実行時に、コサイン距離 0.05 未満（similarity 0.95 以上）の既存記憶がある場合は保存をブロックし、既存記憶の情報をエージェントに返す。記憶ストアへのほぼ同一内容の蓄積を防止する。

## 前提
- `MemoryStore.save_with_auto_link` が動作していること
- `MemoryStore.search` がコサイン距離を返すこと

## 参照
- `design/memory-dedup-design.md` §A

## タスク

### T-800-1: `save_with_auto_link` に重複検出フェーズを追加
対象ファイル: `ego-mcp/src/ego_mcp/memory.py`

`save_with_auto_link` の返り値の型を以下のように拡張する:

**現行:** `tuple[Memory, int, list[MemorySearchResult]]`
**変更後:** `tuple[Memory | None, int, list[MemorySearchResult], MemorySearchResult | None]`

4 番目の要素 `duplicate_of` は、重複が検出された場合に最も類似した既存記憶の `MemorySearchResult` を格納する。重複がない場合は `None`。

**処理の流れ:**
1. `save()` を呼ぶ **前に** `search(content, n_results=1)` で最近傍記憶を検索する
2. 結果が存在し、かつ `distance < dedup_threshold`（デフォルト 0.05）の場合:
   - `save()` を呼ばずに `(None, 0, [], candidates[0])` を返す
3. それ以外は従来通り `save()` → auto-link → `(memory, num_links, linked_results, None)` を返す

`dedup_threshold` はメソッドのキーワード引数として追加する（デフォルト: `0.05`）。

コレクションが空（`count() == 0`）の場合は重複検出をスキップする。

### T-800-2: `_handle_remember` で重複検出時のレスポンスを実装
対象ファイル: `ego-mcp/src/ego_mcp/server.py`

`_handle_remember` 内で `save_with_auto_link` の返り値を 4 要素で受け取るよう修正し、重複検出時の分岐を追加する。

**重複検出時（`mem is None and duplicate_of is not None`）のレスポンス:**

data 部:
```
Not saved — very similar memory already exists.
Existing (id: {id}, {相対時間}): {content 120文字 truncate}
Similarity: {similarity:.2f}
If this is a meaningful update, use recall to review the existing memory and consider whether the new perspective adds value.
```

scaffold 部:
```
Is there truly something new here, or is this a repetition?
If your understanding has deepened, try expressing what changed specifically.
```

`_relative_time` と `_truncate_for_quote` は既存のヘルパーを使用する。`compose_response` でレスポンスを構成する。

重複が検出されなかった場合の処理は既存のままとする。ただし、暗黙の充足（`satisfy_implicit`）は重複検出時には呼ばない（記憶保存が実際に行われていないため）。

### T-800-3: テスト
対象ファイル: `ego-mcp/tests/test_memory.py`, `ego-mcp/tests/test_server.py`

**test_memory.py:**
- `save_with_auto_link` に類似コンテンツを 2 回保存した場合、2 回目の返り値で `mem is None` かつ `duplicate_of is not None` であること
- `dedup_threshold` を超える距離の記憶がある場合は通常通り保存されること
- コレクションが空の場合は重複検出がスキップされ正常に保存されること
- 返り値が 4 要素タプルであること

**test_server.py（または test_integration.py）:**
- 重複検出時のレスポンスに `"Not saved"` と `"very similar memory already exists"` が含まれること
- 重複検出時のレスポンスに既存記憶の ID と similarity が含まれること

## 完了確認
```bash
cd ego-mcp
GEMINI_API_KEY=test-key uv run pytest tests/test_memory.py -k "dedup or duplicate" -v
GEMINI_API_KEY=test-key uv run pytest tests/test_server.py -k "remember" -v
uv run mypy src/ego_mcp/memory.py src/ego_mcp/server.py
```
