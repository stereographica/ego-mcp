# 801: consolidate でのマージ候補検出

## 目的
`consolidate` 実行時に、既存記憶の中からコサイン距離 0.10 未満（similarity 0.90 以上）のペアを検出し、マージ候補としてエージェントに提示する。既に蓄積された類似記憶の整理を促す。

## 前提
- 800（remember 保存前の重複検出ガード）が完了していること
- `ConsolidationEngine.run` と `_handle_consolidate` が動作していること

## 参照
- `design/memory-dedup-design.md` §B

## タスク

### T-801-1: `MergeCandidate` データクラスの追加
対象ファイル: `ego-mcp/src/ego_mcp/consolidation.py`

`ConsolidationStats` の前に `MergeCandidate` データクラスを追加する:

```python
@dataclass(frozen=True)
class MergeCandidate:
    """A pair of memories that are near-duplicates."""
    memory_a_id: str
    memory_b_id: str
    distance: float
    snippet_a: str
    snippet_b: str
```

### T-801-2: `ConsolidationStats` の拡張
対象ファイル: `ego-mcp/src/ego_mcp/consolidation.py`

`ConsolidationStats` に `merge_candidates: tuple[MergeCandidate, ...]` フィールドを追加する（`frozen=True` のため `tuple` を使用）。デフォルト値は空タプル。

`to_dict()` にも `merge_candidates` を含める。各候補は `memory_a_id`, `memory_b_id`, `distance`, `snippet_a`, `snippet_b` のキーを持つ dict に変換する。

### T-801-3: `ConsolidationEngine.run` にマージ候補検出フェーズを追加
対象ファイル: `ego-mcp/src/ego_mcp/consolidation.py`

`run` メソッドに以下のキーワード引数を追加する:
- `merge_threshold: float = 0.10` — マージ候補とみなすコサイン距離の閾値
- `max_merge_candidates: int = 5` — 返すマージ候補の最大数

既存のリプレイ・リンク強化フェーズ（Phase 1）の **後** に、マージ候補検出フェーズ（Phase 2）を追加する:

1. Phase 1 で使った `recent` リスト（window 内の記憶）を流用する
2. 各記憶について `store.search(mem.content, n_results=3)` を実行
3. 自身を除き `distance < merge_threshold` の結果を候補にする
4. 同一ペアの重複を防ぐ（ID のソート済みタプルを seen セットで管理）
5. `max_merge_candidates` に達したら打ち切る
6. 各候補の `snippet_a` / `snippet_b` は `content[:100]` とする

### T-801-4: `_handle_consolidate` のレスポンスを拡張
対象ファイル: `ego-mcp/src/ego_mcp/server.py`

マージ候補がある場合、既存のレスポンスに続けて以下を表示する:

```
Found {N} near-duplicate pair(s):
- {memory_a_id} <-> {memory_b_id} (similarity: {similarity:.2f})
  A: {snippet_a}
  B: {snippet_b}
...

Review each pair with recall. If one is redundant, consider which to keep.
```

マージ候補が 0 件の場合は追加表示しない。

### T-801-5: テスト
対象ファイル: `ego-mcp/tests/test_consolidation.py`

- 類似記憶ペアが存在する場合に `merge_candidates` が検出されること
- `merge_threshold` を超える距離のペアはマージ候補に含まれないこと
- `max_merge_candidates` で候補数が制限されること
- 同一ペアが重複して候補に含まれないこと
- `to_dict()` に `merge_candidates` キーが含まれること
- 類似記憶がない場合に `merge_candidates` が空であること

## 完了確認
```bash
cd ego-mcp
GEMINI_API_KEY=test-key uv run pytest tests/test_consolidation.py -v
GEMINI_API_KEY=test-key uv run pytest tests/test_server.py -k "consolidate" -v
uv run mypy src/ego_mcp/consolidation.py src/ego_mcp/server.py
```
