# forget ツール設計

> 関連: [memory-dedup-design.md](./memory-dedup-design.md) / [idea.md](./idea.md) / [tool-design.md](./tool-design.md)
> Issue: #16

## 背景

v0.2.2 で追加された `consolidate` のマージ候補検出により、類似度の高い重複記憶ペアが検出されるようになった。また、`remember` の保存前ガード（similarity 0.95 以上でブロック）により新規の重複は防げるが、**既存の重複を削除する手段がない**。

### 実際に検出された重複例

```
- mem_651b9d294720 <-> mem_ecb99b9f9cc0 (similarity: 0.93) — Blue Envelope #14 の記憶が3重保存
- mem_44bd699727e4 <-> mem_aac6cc183448 (similarity: 0.97) — ハートビート内省が3重保存
```

### ユースケース

1. `consolidate` でマージ候補が見つかった後、重複を手動で削除
2. 誤って保存された記憶の修正（削除→再保存）
3. 古くなった記憶の明示的な削除

### 現状の制約

`MemoryStore` には `delete` メソッドが存在しない。ChromaDB 自体は `collection.delete(ids=[...])` をサポートしているが、ego-mcp のアプリケーション層では未使用。記憶の削除は以下の 4 つの整合性問題を引き起こすため、単純な ChromaDB 削除では不十分:

1. **双方向リンクの孤立** — 削除対象を参照する他記憶のリンクが宙に浮く
2. **エピソードの参照断絶** — `Episode.memory_ids` に含まれる ID が無効になる
3. **Workspace ファイルの不整合** — 同期済みの Markdown エントリが残る
4. **記憶内容の不可逆的消失** — 削除確認なしでは危険

---

## 設計方針

| 施策 | 概要 | 目的 |
|------|------|------|
| **A. `MemoryStore.delete` メソッド** | ChromaDB 削除 + 双方向リンクのクリーンアップ | データ層の整合性保証 |
| **B. Workspace Sync のエントリ除去** | `[id:memory_id]` マーカーを持つ行の削除 | 同期済みファイルの整合性 |
| **C. エピソード参照のクリーンアップ** | 削除された memory_id を `Episode.memory_ids` から除去 | エピソードの整合性 |
| **D. `forget` ツールの追加** | サーバーツールとしての公開・ハンドラ実装 | エージェントからのアクセス手段 |
| **E. スキャフォールドの整備** | `consolidate` のマージ候補提示に `forget` への導線を追加 | 既存ワークフローとの接続 |

---

## A. `MemoryStore.delete` メソッド

### 設計思想

記憶の削除は「忘れる」行為であり、ego-mcp の認知アーキテクチャにおいて重要な操作。削除対象の記憶だけでなく、その記憶に接続された全てのリンクを適切に処理しなければ、記憶ネットワークの整合性が壊れる。

### 双方向リンクの問題

現在の `link_memories()` は双方向にリンクを作成する:

```
Memory A (linked_ids: [{target_id: "B", ...}])
Memory B (linked_ids: [{target_id: "A", ...}])
```

Memory A を削除する場合、Memory B の `linked_ids` から A への参照を除去しなければならない。

### 逆方向リンクの探索

ChromaDB はリレーショナル DB のような逆引きインデックスを持たない。`linked_ids` は各記憶の metadata に JSON として格納されているため、「Memory A を参照している記憶」を効率的に検索する手段がない。

**選択肢:**

| 方式 | 概要 | 計算量 | 正確性 |
|------|------|--------|--------|
| **A-1. 全件スキャン** | 全記憶を取得し、`linked_ids` を走査 | O(n) | 完全 |
| **A-2. 順方向リンクのみ処理** | 削除対象の `linked_ids` に含まれるターゲットの逆リンクを除去 | O(k) (k = リンク数) | 完全 |
| **A-3. 遅延クリーンアップ** | 削除のみ行い、参照先は次回アクセス時に除去 | O(1) | 結果的整合性 |

**A-2 を採用する。**

理由:
- `link_memories()` は常に双方向リンクを作成する。したがって、Memory A が B にリンクしていれば、B も A にリンクしている。削除対象の `linked_ids` を走査するだけで、全ての逆リンクを特定できる
- 全件スキャン（A-1）は記憶数の増加に比例してコストが上がり、通常の削除操作には過剰
- 遅延クリーンアップ（A-3）は整合性保証が弱く、`recall` や `introspect` で無効な ID が表示されるリスクがある

**A-2 が成立する前提:** 双方向リンクの不変条件（A→B ならば B→A）が常に保たれていること。現在の `link_memories()`, `save_with_auto_link()`, `bump_link_confidence()` は全てこの不変条件を維持している。

### `MemoryStore.delete` の実装方針

```python
async def delete(self, memory_id: str) -> Memory | None:
    """Delete a memory and clean up all bidirectional links.

    Returns the deleted Memory (for confirmation display), or None if
    the memory was not found.
    """
    collection = self._ensure_connected()

    # 1. Retrieve the memory to delete (also serves as existence check)
    memory = await self.get_by_id(memory_id)
    if memory is None:
        return None

    # 2. Clean up reverse links in all linked targets
    for link in memory.linked_ids:
        target = await self.get_by_id(link.target_id)
        if target is None:
            continue  # Target already deleted or missing
        cleaned_links = [
            lk for lk in target.linked_ids if lk.target_id != memory_id
        ]
        collection.update(
            ids=[link.target_id],
            metadatas={"linked_ids": _links_to_json(cleaned_links)},
        )

    # 3. Delete from ChromaDB
    collection.delete(ids=[memory_id])

    return memory
```

**設計上のポイント:**

- 返り値は削除された `Memory`（確認表示用）。見つからない場合は `None`
- Step 2 で逆リンクをクリーンアップしてから Step 3 で削除する順序が重要。逆順だと、他の並行処理が Step 2 の途中で削除済みの記憶を参照する可能性がある（ただし現在は並行処理の考慮は不要）
- `target` が `None` の場合（既に削除済み）はスキップ。防御的処理

### Association Engine への影響

`AssociationEngine.spread()` は `get_by_id()` が `None` を返した場合にスキップして続行する（`association.py` L52-53）。したがって、記憶の削除後も association engine は正常に動作する。ただし、削除された記憶への `linked_ids` が残存している場合、無駄な `get_by_id()` 呼び出しが発生する。A-2 方式で逆リンクを除去することで、この問題も解消される。

---

## B. Workspace Sync のエントリ除去

### 現状の同期パターン

`WorkspaceMemorySync` は記憶の保存時に以下のファイルに追記する:

| ファイル | パス | 条件 | マーカー形式 |
|---------|------|------|-------------|
| Daily log | `memory/{YYYY-MM-DD}.md` | 常に | `[id:{memory_id}]` |
| Curated memory | `MEMORY.md` | `importance >= 4` or `category in CURATION_CATEGORIES` | `[id:{memory_id}]` |
| Latest monologue | `memory/inner-monologue-latest.md` | `category == INTROSPECTION` | なし（上書き） |

全てのエントリは `[id:{memory_id}]` マーカーで識別可能（latest monologue を除く）。

### 除去の方針

`WorkspaceMemorySync` に `remove_memory(memory_id: str)` メソッドを追加する。

```python
def remove_memory(self, memory_id: str) -> bool:
    """Remove all traces of a memory from workspace files.

    Returns True if any file was modified.
    """
    marker = f"[id:{memory_id}]"
    modified = False

    # 1. Clean daily logs
    for daily_file in self._memory_dir.glob("????-??-??.md"):
        if self._remove_lines_with_marker(daily_file, marker):
            modified = True

    # 2. Clean curated memory
    if self._remove_lines_with_marker(self._curated_memory, marker):
        modified = True

    return modified

def _remove_lines_with_marker(self, path: Path, marker: str) -> bool:
    """Remove lines containing the marker from a file.

    Returns True if the file was modified.
    """
    if not path.exists():
        return False

    content = path.read_text(encoding="utf-8")
    if marker not in content:
        return False

    lines = content.split("\n")
    cleaned = [line for line in lines if marker not in line]
    path.write_text("\n".join(cleaned), encoding="utf-8")
    return True
```

**設計上のポイント:**

- `_remove_lines_with_marker` を汎用ヘルパーとして切り出し、daily log と curated memory で再利用
- Daily log のファイル名パターン `????-??-??.md` でマッチ。これにより他の Markdown ファイル（README 等）を誤って操作しない
- `latest monologue` は除去対象外。このファイルは最新の内省を上書きする設計であり、過去の記憶 ID を含まない。削除対象が最新の内省だった場合、次回の内省で自然に上書きされる
- ファイルが存在しない場合やマーカーが見つからない場合はスキップ（防御的処理）
- Workspace Sync はオプション機能（`EGO_MCP_WORKSPACE_DIR` 未設定なら無効）。削除時も同様に、Sync が有効な場合のみ実行

---

## C. エピソード参照のクリーンアップ

### 現状の `Episode` 構造

```python
@dataclass
class Episode:
    id: str
    summary: str
    memory_ids: list[str]  # 記憶 ID のリスト
    start_time: str
    end_time: str
    importance: int
```

`memory_ids` は記憶の ID をスナップショットとして保持する。記憶が削除されると、ここに無効な ID が残る。

### クリーンアップの選択肢

| 方式 | 概要 | 利点 | 欠点 |
|------|------|------|------|
| **C-1. 即時除去** | 削除時にエピソードから memory_id を除去 | 即座に整合性が保たれる | エピソードの全件スキャンが必要 |
| **C-2. 遅延除去** | エピソード取得時に無効な ID をフィルタ | 削除時のコストゼロ | `get_episode` の結果が実態と乖離する期間が生じる |
| **C-3. 何もしない** | 無効な ID はそのまま残す | 実装コストゼロ | `get_episode` で存在しない記憶が参照される |

**C-2（遅延除去）を採用する。**

理由:
- エピソードの全件スキャンは記憶削除の度に発生するコストとしては過剰
- エピソードの `memory_ids` は参照であり、実体ではない。無効な ID があっても `get_by_id()` が `None` を返すだけで、致命的なエラーは発生しない
- `get_episode` ハンドラで `memory_ids` をフィルタすれば、エージェントには常に有効な ID のみが見える
- エピソード数は記憶数に比べて少なく（重要なイベントのみ作成される）、遅延除去のコストは十分に低い

### `_handle_get_episode` の変更

```python
# 既存の get_episode レスポンスに、memory_ids の有効性検証を追加
memory_ids = episode.memory_ids
valid_ids = []
for mid in memory_ids:
    mem = await memory.get_by_id(mid)
    if mem is not None:
        valid_ids.append(mid)

# 削除された記憶があった場合のみ注記
if len(valid_ids) < len(memory_ids):
    lines.append(f"Note: {len(memory_ids) - len(valid_ids)} memory(ies) no longer exist.")
```

**将来的な最適化:** エピソード数が増えた場合、バックグラウンドでの定期的なクリーンアップ（`consolidate` の一部として）を検討できる。現時点ではスコープ外。

---

## D. `forget` ツール

### ツール分類

**BACKEND_TOOLS に配置する。**

理由:
- `forget` は `consolidate` のマージ候補検出を起点として使われる。`consolidate` のスキャフォールドから誘導されるフロー
- Surface Tool は「エージェントの自発的な認知活動」を表す。記憶の削除は認知活動ではなく、整理のための操作
- `link_memories` と同じカテゴリ（記憶管理の操作的ツール）

### インターフェース

```json
{
  "name": "forget",
  "description": "Delete a memory by ID. Returns the deleted memory's summary for confirmation.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "memory_id": {
        "type": "string",
        "description": "ID of the memory to delete"
      }
    },
    "required": ["memory_id"]
  }
}
```

**設計上のポイント:**

- 単一の `memory_id` のみ受け付ける。バッチ削除は誤操作リスクが高く、エージェントが 1 件ずつ確認しながら削除する運用が望ましい
- `confirm` パラメータは設けない。ツール呼び出し自体がエージェントの意思決定であり、二重確認は過剰。代わりに、レスポンスに削除された記憶の内容を表示し、事後確認を促す

### `_handle_forget` の実装方針

```python
async def _handle_forget(
    memory: MemoryStore,
    args: dict[str, Any],
) -> str:
    """Delete a memory and clean up all references."""
    memory_id = args["memory_id"]

    deleted_memory = await memory.delete(memory_id)

    if deleted_memory is None:
        data = f"Memory not found: {memory_id}"
        scaffold = "Double-check the ID. Use recall to search for the memory you're looking for."
        return compose_response(data, scaffold)

    # Workspace sync cleanup (best-effort)
    sync = _get_workspace_sync()
    if sync is not None and not deleted_memory.is_private:
        try:
            sync.remove_memory(memory_id)
        except OSError:
            logger.warning("Workspace cleanup failed for %s", memory_id)

    age = _relative_time(deleted_memory.timestamp)
    snippet = _truncate_for_quote(deleted_memory.content, limit=120)
    data = (
        f"Forgot (id: {memory_id}, {age}): {snippet}\n"
        f"Emotion: {deleted_memory.emotional_trace.primary.value} | "
        f"Importance: {deleted_memory.importance}"
    )
    scaffold = (
        "This memory is gone. Was there anything worth preserving in a new form?\n"
        "If this was part of a merge, save the consolidated version with remember."
    )
    return compose_response(data, scaffold)
```

**レスポンス例（正常）:**

```
Forgot (id: mem_651b9d294720, 3d ago): Blue Envelope #14 の記憶 ...
Emotion: happy | Importance: 3

---
This memory is gone. Was there anything worth preserving in a new form?
If this was part of a merge, save the consolidated version with remember.
```

**レスポンス例（ID 不存在）:**

```
Memory not found: mem_invalid123

---
Double-check the ID. Use recall to search for the memory you're looking for.
```

### 暗黙の充足（Implicit Satisfaction）

`forget` は **暗黙の充足マッピングに含めない**。

理由:
- 記憶の削除は認知活動（表現、探索、内省）ではなく、整理操作
- 削除で欲求が充足されるのは意味的に不自然
- `consolidate` がトリガーとなるフローでは、`consolidate` 自体が `cognitive_coherence` を部分充足済み

### `_dispatch` への追加

```python
elif name == "forget":
    return await _handle_forget(memory, args)
    # Note: No satisfy_implicit call
```

---

## E. スキャフォールド改善

### `consolidate` のマージ候補提示に `forget` への導線を追加

現在の `_handle_consolidate` のマージ候補表示:

```
Found 1 near-duplicate pair(s):
- mem_a1b2c3d4 <-> mem_e5f6g7h8 (similarity: 0.93)
  A: Today's conversation was fun. I learned a lot from Master.
  B: Today's conversation was enjoyable. Master taught me many things.

Review each pair with recall. If one is redundant, consider which to keep.
```

**新しいスキャフォールド:**

```
Found 1 near-duplicate pair(s):
- mem_a1b2c3d4 <-> mem_e5f6g7h8 (similarity: 0.93)
  A: Today's conversation was fun. I learned a lot from Master.
  B: Today's conversation was enjoyable. Master taught me many things.

Review each pair with recall. If one is redundant, use forget to remove it.
If both have value, consider which perspective to keep.
```

### 変更の意図

| | 旧 | 新 |
|---|---|---|
| アクション | 「consider which to keep」（考えるだけ） | 「use forget to remove it」（具体的な手段の提示） |
| 認知の型 | 思考で止まる | 思考 → 行動の接続 |

v0.2.2 時点では `forget` が存在しなかったため、「consider which to keep」で止めていた。`forget` の追加により、検出→判断→削除の完結したワークフローが成立する。

---

## 実装スコープ

### 変更対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `ego-mcp/src/ego_mcp/memory.py` | `MemoryStore.delete()` メソッドを追加 |
| `ego-mcp/src/ego_mcp/workspace_sync.py` | `remove_memory()`, `_remove_lines_with_marker()` メソッドを追加 |
| `ego-mcp/src/ego_mcp/server.py` | `forget` ツール定義を `BACKEND_TOOLS` に追加、`_handle_forget` ハンドラ追加、`_dispatch` に分岐追加、`_handle_get_episode` に memory_ids フィルタ追加 |
| `ego-mcp/docs/tool-reference.md` | `forget` ツールのリファレンスを追加 |
| `ego-mcp/tests/test_memory.py` | `delete()` のテスト（正常削除、逆リンク除去、存在しない ID、リンクなし記憶） |
| `ego-mcp/tests/test_workspace_sync.py` | `remove_memory()` のテスト（daily log 除去、curated 除去、ファイル不存在） |
| `ego-mcp/tests/test_server.py` | `_handle_forget` のテスト（正常削除、ID 不存在、workspace sync 連携） |

### 後方互換性

- `MemoryStore` に `delete()` メソッドが追加される（追加的変更、既存 API に影響なし）
- `WorkspaceMemorySync` に `remove_memory()`, `_remove_lines_with_marker()` が追加される（追加的変更）
- `BACKEND_TOOLS` に `forget` が追加される（追加的変更、既存ツールに影響なし）
- `_handle_get_episode` の memory_ids フィルタは表示上の変更であり、`Episode` データ自体は変更しない
- 既存の記憶データ・エピソードデータに対するマイグレーションは不要

### バージョニング

本変更は機能追加であり、既存のデータ形式に破壊的変更がないため、パッチバージョンの更新で対応する。

- `ego-mcp/pyproject.toml`: `version` → `"0.2.3"`
- `ego-mcp/src/ego_mcp/__init__.py`: `__version__` → `"0.2.3"`

---

## ツールフロー（更新後）

```
Memory Management (updated):
  consolidate → [merge candidates detected] → recall → forget → [remember merged version]

Deletion flow:
  recall(context) → identify target → forget(memory_id) → [optional: remember(new version)]
```

---

## 将来の拡張

| 項目 | 概要 | 前提 |
|------|------|------|
| `merge_memories` ツール | `forget` + `remember` を 1 操作で行うショートカット | `forget` と `remember` の運用実績を見てから判断 |
| バッチ削除 | 複数の `memory_id` を一度に削除 | 運用上の必要性が確認された場合 |
| エピソードの定期クリーンアップ | `consolidate` 内で無効な memory_ids を除去 | エピソード数が増加した場合 |
| 削除ログ | 削除された記憶の履歴を保持 | 監査・復元の必要性が生じた場合 |
