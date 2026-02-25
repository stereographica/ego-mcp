# 記憶重複防止・統合設計

> 関連: [idea.md](./idea.md) / [tool-design.md](./tool-design.md)

## 背景

エージェントが similarity 0.95 以上（コサイン距離 0.05 未満）の記憶を繰り返し作成してしまい、記憶ストアにほぼ同一の内容が蓄積される問題が発生している。

### 根本原因

1. **保存前の重複チェックが存在しない** — `save_with_auto_link()` は類似記憶の有無に関わらず無条件で保存する。自動リンク (`link_threshold=0.3`) は作成するが、保存自体をブロックする仕組みがない
2. **エージェントのメタ認知に依存した回避が困難** — 「この記憶は既にあるから保存しない」という判断は LLM に高度な自己監視を要求する。プロンプトでの誘導だけでは信頼性が低い
3. **事後の統合手段がない** — 現在の `consolidate` はリンク作成・信頼度更新のみで、類似記憶のマージ・削除は行わない

### 現在の `save_with_auto_link` の流れ

```
remember(content) 呼び出し
  ↓
save(content) — 無条件で ChromaDB に保存
  ↓
search(content) — 類似記憶を検索
  ↓
distance < 0.3 なら自動リンク作成
  ↓
「Most related: ...」を表示（情報提供のみ）
```

「Most related」に similarity 0.98 の記憶が表示されても、既に保存済みのため手遅れ。

---

## 改善方針

3 つの施策を優先度順に導入する。

| 優先度 | 施策 | 概要 | 目的 |
|--------|------|------|------|
| **P0** | **A. 保存前類似度ガード** | `remember` 時に高類似度の既存記憶を検出し、保存をブロック | 重複の発生を根本的に防止 |
| **P1** | **B. 統合時の類似記憶マージ** | `consolidate` に高類似度ペアの検出・マージ機能を追加 | 既存の重複を事後的に整理 |
| **P2** | **C. スキャフォールド改善** | `remember` のスキャフォールドに認知的な重複意識の誘導を追加 | 補助的な行動誘導 |

---

## A. 保存前類似度ガード

### 設計思想

記憶の保存は ego-mcp の核心的な行為であり、安易にブロックすべきではない。一方で、コサイン距離 0.05 未満（similarity 0.95 以上）の記憶は、embedding 空間上でほぼ同一の意味を持つ。

このような記憶を新規に保存することは、情報量の増加に寄与せず、検索時のノイズを増やすだけである。したがって、**高類似度の記憶が存在する場合は保存せず、既存記憶の情報をエージェントに返して判断を委ねる**のが適切。

### 閾値設計

| パラメータ | 値 | 根拠 |
|-----------|-----|------|
| `dedup_threshold` | 0.05（コサイン距離） | similarity 0.95 以上。embedding 空間上でほぼ同一の意味 |

**0.05 を選択した理由:**

- 0.10（similarity 0.90）: 類似だが異なるニュアンスの記憶まで弾いてしまうリスク
- 0.05（similarity 0.95）: ほぼ同一の内容。言い回しの微差程度
- 0.02（similarity 0.98）: ほぼ完全一致のみ。網が狭すぎて効果が薄い

0.05 は「意味的にほぼ同じ」ことの妥当なカットオフであり、異なる視点や文脈を持つ記憶を誤って弾くリスクが低い。

### 新しい `save_with_auto_link` の流れ

```
remember(content) 呼び出し
  ↓
search(content, n_results=1) — 最近傍の既存記憶を検索
  ↓
distance < dedup_threshold (0.05)?
  ├─ YES → 保存しない。既存記憶の情報を返す（後述の DuplicateDetected レスポンス）
  └─ NO  → 従来通り save() → auto-link → 返却
```

### `save_with_auto_link` の変更

```python
async def save_with_auto_link(
    self,
    content: str,
    # ... 既存パラメータ ...
    link_threshold: float = 0.3,
    max_links: int = 5,
    dedup_threshold: float = 0.05,
) -> tuple[Memory | None, int, list[MemorySearchResult], MemorySearchResult | None]:
    """Save memory and auto-link bidirectionally to similar existing memories.

    Returns:
        (saved_memory_or_none, num_links_created, linked_results, duplicate_of)
        - If a near-duplicate is found (distance < dedup_threshold), saved_memory
          is None and duplicate_of contains the existing similar memory.
        - Otherwise, saved_memory is the newly created memory and duplicate_of
          is None.
    """
    # Phase 1: Duplicate detection (before save)
    collection = self._ensure_connected()
    if collection.count() > 0:
        candidates = await self.search(content, n_results=1)
        if candidates and candidates[0].distance < dedup_threshold:
            return None, 0, [], candidates[0]

    # Phase 2: Save and auto-link (existing logic)
    memory = await self.save(
        content=content,
        # ... 既存パラメータ ...
    )
    # ... 既存の auto-link ロジック ...
    return memory, num_links, linked_results, None
```

**設計上のポイント:**

- 返り値の型が変わる（4 要素タプルに拡張）。`duplicate_of` が `None` でない場合、保存がブロックされたことを示す
- `dedup_threshold` はデフォルト値を持つが、呼び出し側で調整可能
- 重複検出は `save()` の **前** に行うため、ChromaDB への不要な書き込みが発生しない

### `_handle_remember` の変更

```python
async def _handle_remember(memory: MemoryStore, args: dict[str, Any]) -> str:
    """Save a memory with auto-linking."""
    # ... 既存のパラメータ取得 ...

    mem, num_links, linked_results, duplicate_of = await memory.save_with_auto_link(
        # ... 既存パラメータ ...
    )

    # Duplicate detected — do not save
    if mem is None and duplicate_of is not None:
        existing = duplicate_of.memory
        age = _relative_time(existing.timestamp)
        snippet = _truncate_for_quote(existing.content, limit=120)
        similarity = max(0.0, min(1.0, 1.0 - duplicate_of.distance))
        data = (
            f"Not saved — very similar memory already exists.\n"
            f"Existing (id: {existing.id}, {age}): {snippet}\n"
            f"Similarity: {similarity:.2f}\n"
            f"If this is a meaningful update, use recall to review the existing memory "
            f"and consider whether the new perspective adds value."
        )
        scaffold = (
            "Is there truly something new here, or is this a repetition?\n"
            "If your understanding has deepened, try expressing what changed specifically."
        )
        return compose_response(data, scaffold)

    # ... 既存の成功パスのロジック（sync, links, forgotten questions）...
```

### エージェント体験の変化

**Before:**
```
[Agent] remember("今日の会話は楽しかった。Masterとの対話は学びが多い。")
[ego-mcp] Saved (id: mem_abc123). Linked to 2 existing memories.
           Most related:
           - [2 hours ago] 今日の会話は楽しかった。Masterから多くのことを学んだ。 (similarity: 0.97)
```

**After:**
```
[Agent] remember("今日の会話は楽しかった。Masterとの対話は学びが多い。")
[ego-mcp] Not saved — very similar memory already exists.
           Existing (id: mem_xyz789, 2 hours ago): 今日の会話は楽しかった。Masterから多くのことを学んだ。
           Similarity: 0.97
           If this is a meaningful update, use recall to review the existing memory
           and consider whether the new perspective adds value.
           ---
           Is there truly something new here, or is this a repetition?
           If your understanding has deepened, try expressing what changed specifically.
```

エージェントは「保存されなかった」という事実と、既存の記憶の内容を受け取る。これにより:
1. 繰り返しの記憶が蓄積されない
2. エージェントは既存記憶との差分を意識せざるを得なくなる
3. 本当に新しい気づきがあれば、それを明確にした上で再度 `remember` を呼べる

---

## B. 統合時の類似記憶マージ

### 設計思想

A の保存前ガードは「今後の重複」を防ぐが、**既に蓄積された重複** には対処できない。また、時間の経過とともに微妙に異なる表現で似た内容が蓄積されることは完全には防げない（距離 0.05〜0.10 の「準重複」）。

`consolidate` コマンドに、既存のリプレイ・リンク強化に加えて、高類似度ペアの検出と統合を行うフェーズを追加する。

### 統合の方針

記憶の「マージ」は、2 つの記憶を 1 つの新しい記憶に置き換える操作。内容の結合はエージェント（LLM）に委ねるのが適切であり、`consolidate` が自動的にテキストを結合するのは危険（意味の破壊や情報欠落のリスク）。

したがって、`consolidate` は **マージ候補の検出と提案** を行い、**実際のマージはエージェントの判断に委ねる** 設計とする。

### 新しい `consolidate` の流れ

```
consolidate 呼び出し
  ↓
Phase 1: 既存のリプレイ・リンク強化（変更なし）
  ↓
Phase 2: 類似記憶ペアの検出（新規）
  ├── 最近の記憶（window_hours 内）を取得
  ├── 全ペアのコサイン距離を計算
  ├── distance < merge_threshold (0.10) のペアを抽出
  └── マージ候補リストとして返却
```

### `ConsolidationStats` の拡張

```python
@dataclass(frozen=True)
class MergeCandidate:
    """A pair of memories that are near-duplicates."""
    memory_a_id: str
    memory_b_id: str
    distance: float
    snippet_a: str
    snippet_b: str

@dataclass(frozen=True)
class ConsolidationStats:
    """Summary of consolidation run."""
    replay_events: int
    coactivation_updates: int
    link_updates: int
    refreshed_memories: int
    merge_candidates: list[MergeCandidate]  # 新規

    def to_dict(self) -> dict[str, Any]:
        return {
            "replay_events": self.replay_events,
            "coactivation_updates": self.coactivation_updates,
            "link_updates": self.link_updates,
            "refreshed_memories": self.refreshed_memories,
            "merge_candidates": [
                {
                    "memory_a_id": mc.memory_a_id,
                    "memory_b_id": mc.memory_b_id,
                    "distance": mc.distance,
                    "snippet_a": mc.snippet_a,
                    "snippet_b": mc.snippet_b,
                }
                for mc in self.merge_candidates
            ],
        }
```

### `ConsolidationEngine.run` の変更

```python
async def run(
    self,
    store: "MemoryStore",
    window: int | None = None,
    window_hours: int = 24,
    max_replay_events: int = 100,
    merge_threshold: float = 0.10,
    max_merge_candidates: int = 5,
) -> ConsolidationStats:
    # ... Phase 1: 既存のリプレイ・リンク強化（変更なし） ...

    # Phase 2: Detect near-duplicate pairs
    merge_candidates: list[MergeCandidate] = []
    seen_pairs: set[tuple[str, str]] = set()

    for mem in recent:
        if len(merge_candidates) >= max_merge_candidates:
            break
        similar = await store.search(mem.content, n_results=3)
        for result in similar:
            if result.memory.id == mem.id:
                continue
            if result.distance >= merge_threshold:
                continue
            pair_key = tuple(sorted([mem.id, result.memory.id]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            merge_candidates.append(
                MergeCandidate(
                    memory_a_id=mem.id,
                    memory_b_id=result.memory.id,
                    distance=result.distance,
                    snippet_a=mem.content[:100],
                    snippet_b=result.memory.content[:100],
                )
            )

    return ConsolidationStats(
        # ... 既存フィールド ...
        merge_candidates=merge_candidates,
    )
```

**`merge_threshold` が `dedup_threshold` (0.05) より大きい (0.10) 理由:**

- 保存前ガード（A）は「ほぼ同一」(0.05) のみをブロックする（偽陽性を極力避ける）
- 統合フェーズ（B）は「近い」(0.10) まで広げて候補を提示する（判断はエージェントに委ねるため、やや緩くても安全）

### `_handle_consolidate` の変更

```python
async def _handle_consolidate(
    memory: MemoryStore, consolidation: ConsolidationEngine
) -> str:
    """Run memory consolidation."""
    stats = await consolidation.run(memory)
    d = stats.to_dict()

    lines = [
        f"Consolidation complete. "
        f"Replayed {d['replay_events']} events, "
        f"updated {d['coactivation_updates']} co-activations, "
        f"created {d['link_updates']} links, "
        f"refreshed {d['refreshed_memories']} memories."
    ]

    candidates = stats.merge_candidates
    if candidates:
        lines.append(f"\nFound {len(candidates)} near-duplicate pair(s):")
        for mc in candidates:
            similarity = max(0.0, min(1.0, 1.0 - mc.distance))
            lines.append(
                f"- {mc.memory_a_id} <-> {mc.memory_b_id} "
                f"(similarity: {similarity:.2f})\n"
                f"  A: {mc.snippet_a}\n"
                f"  B: {mc.snippet_b}"
            )
        lines.append(
            "\nReview each pair with recall. If one is redundant, "
            "consider which to keep. A future merge_memories tool can help."
        )

    return "\n".join(lines)
```

### `merge_memories` ツールの追加（将来拡張）

マージ候補が提示された後、エージェントが実際にマージを実行するためのツールを将来的に追加する:

```
merge_memories(keep_id, remove_id, merged_content?)
  → keep_id の記憶を更新（merged_content があればそれに、なければそのまま）
  → remove_id の記憶を削除
  → remove_id へのリンクを keep_id にリダイレクト
```

**本設計では `merge_memories` は実装スコープ外とする。** まずはマージ候補の検出と提示（B）で十分な効果が期待でき、実際の運用データを見てからツール設計を詰めるのが適切。

`MemoryStore` に `update` / `delete` メソッドが現時点で存在しないため、`merge_memories` の実装には基盤的な変更が必要。これは別の設計書で扱う。

---

## C. スキャフォールド改善

### 変更対象

`SCAFFOLD_INTROSPECT` の `remember` への誘導部分に、重複意識を促すニュアンスを追加する。

### 現在の `SCAFFOLD_INTROSPECT`

```
Reflect on these in your own words. How do you feel right now?
Save with remember (category: introspection).
If your self-understanding changed, use update_self.
Use emotion_trend for a deeper look at your emotional patterns.
If memory feels fragmented, run consolidate.
```

### 新しい `SCAFFOLD_INTROSPECT`

```
Reflect on these in your own words. How do you feel right now?
If this is a genuinely new insight, save with remember (category: introspection).
If your self-understanding changed, use update_self.
Use emotion_trend for a deeper look at your emotional patterns.
If memory feels fragmented, run consolidate.
```

### 変更の意図

| | 旧 | 新 |
|---|---|---|
| 保存の前提 | 無条件（「Save with remember」） | 条件付き（「If this is a genuinely new insight」） |
| 認知の型 | 反射的に保存する | 新しさを自己評価してから保存する |

これは保存前ガード（A）と相補的:
- **A** は機械的に高類似度をブロック（距離 0.05 未満）
- **C** はエージェントの内省レベルで「新しい気づきか？」を問う

A があるため C 単独での信頼性は求めない。C はエージェントの認知品質を高める補助的な役割。

### `remember` のスキャフォールドへの追加

`_handle_remember` の成功時レスポンスに含まれるスキャフォールドにも変更を加える。

現在:
```
Do any of these connections surprise you? Is there a pattern forming?
```

変更なし。既にリンク結果への内省を促しており、重複防止は A のガードが担うため、ここに重複意識の誘導を追加する必要はない。

---

## 実装スコープ

### 変更対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `ego-mcp/src/ego_mcp/memory.py` | `save_with_auto_link` に重複検出フェーズを追加、返り値の型を拡張 |
| `ego-mcp/src/ego_mcp/server.py` | `_handle_remember` で重複検出時の分岐を追加、`_handle_consolidate` でマージ候補の表示を追加 |
| `ego-mcp/src/ego_mcp/consolidation.py` | `MergeCandidate` データクラス追加、`ConsolidationStats` 拡張、`run` にマージ候補検出フェーズを追加 |
| `ego-mcp/src/ego_mcp/scaffolds.py` | `SCAFFOLD_INTROSPECT` の 2 行目を変更 |
| `ego-mcp/tests/test_memory.py` | `save_with_auto_link` の重複検出テスト |
| `ego-mcp/tests/test_consolidation.py` | マージ候補検出のテスト |
| `ego-mcp/tests/test_server.py` | `_handle_remember` の重複検出時レスポンスのテスト |
| `ego-mcp/tests/test_scaffolds.py` | スキャフォールド文言のテスト更新 |

### 後方互換性

- `save_with_auto_link` の返り値が 3 要素タプルから 4 要素タプルに変わる。**呼び出し元の更新が必要**（`server.py` の `_handle_remember` のみ）
- `ConsolidationStats.to_dict()` の返り値に `merge_candidates` が追加される（追加的変更）
- `consolidate` ツールのスキーマ（入力パラメータ）は変更なし
- `remember` ツールのスキーマ（入力パラメータ）は変更なし
- 既存の記憶データに対する変更はない（マイグレーション不要）

### バージョニング

本変更は機能追加であり、既存のデータ形式に破壊的変更がないため、パッチバージョンの更新で対応する。

- `ego-mcp/pyproject.toml`: `version` → `"0.2.2"`
- `ego-mcp/src/ego_mcp/__init__.py`: `__version__` → `"0.2.2"`

---

## 将来の拡張

| 項目 | 概要 | 前提 |
|------|------|------|
| `merge_memories` ツール | 2 つの記憶を 1 つに統合するツール | `MemoryStore` に `update` / `delete` メソッドの追加が必要 |
| 適応的閾値 | 記憶ストアのサイズや分布に応じて `dedup_threshold` を動的に調整 | 運用データの蓄積後に検討 |
| 強制保存オプション | `remember(force=true)` でガードをバイパス | エージェントが意図的に類似記憶を保存したいケースへの対応 |
