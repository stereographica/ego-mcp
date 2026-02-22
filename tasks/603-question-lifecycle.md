# 603: 未解決の問い — 解決・重要度・忘却

## 目的
未解決の問い（unresolved questions）に重要度と忘却メカニズムを導入する。重要度が低く古い問いは意識から消えるが、記録は残り、関連文脈が現れれば再浮上できるようにする。

## 前提
- `SelfModelStore` に `add_question` / `resolve_question` が実装済みであること
- `_handle_introspect` が `unresolved_questions` を表示していること

## 参照
- `design/phase3-enhancements.md` §4

## タスク

### T-603-1: `question_log` エントリに `importance` と `created_at` を追加
対象ファイル: `src/ego_mcp/self_model.py`

`add_question` メソッドを拡張する:
- `importance: int = 3` パラメータを追加（1-5、クランプ適用）
- `created_at` フィールドに UTC ISO 8601 タイムスタンプを自動付与
- 既存の question_log エントリに `importance`/`created_at` がない場合のフォールバック処理を追加（デフォルト `importance=3`、`created_at="""`）

### T-603-2: `resolve_question` を `update_self` から呼べるようにする
対象ファイル: `src/ego_mcp/server.py`

`_handle_update_self` を拡張し、`field="resolve_question"` の場合に `SelfModelStore.resolve_question(value)` を呼ぶ分岐を追加する。

同様に `field="question_importance"` の場合に、指定された question の importance を更新する分岐を追加する。`value` は `{"id": "q_xxx", "importance": 5}` の形式を想定する。

### T-603-3: salience 計算関数を実装
対象ファイル: `src/ego_mcp/self_model.py`

```python
def _calculate_salience(importance: int, age_days: float) -> float:
```

- 半減期は `importance * 14` 日（importance=5 → ~70日、importance=1 → ~14日）
- 計算式: `(importance / 5.0) * math.exp(-age_days / half_life)`
- 閾値: `> 0.3` = Active、`0.1 < s <= 0.3` = Fading、`<= 0.1` = Dormant

### T-603-4: `get_visible_questions` メソッドを実装
対象ファイル: `src/ego_mcp/self_model.py`

`SelfModelStore` に以下のメソッドを追加:

```python
def get_visible_questions(self, max_active: int = 5, max_resurfacing: int = 2) -> tuple[list[dict], list[dict]]:
```

- question_log から未解決の問いを取得し、salience を計算
- Active（salience > 0.3）を salience 降順で `max_active` 件返す
- Fading（0.1 < salience <= 0.3）を salience 降順で `max_resurfacing` 件返す
- Dormant（salience <= 0.1）は返さない
- 各エントリに `salience` と `age_days` を付加して返す

### T-603-5: `_handle_introspect` の問い表示を改修
対象ファイル: `src/ego_mcp/server.py`

現行: `unresolved_questions`（ID リスト）から最大 3 件を表示。テキスト内容は表示していない。

改修後: `get_visible_questions` を使い、Active な問いと Resurfacing な問いを別セクションで表示する。

```
Unresolved questions:
- [q_abc123] What's the ideal way to express concern? (importance: 5)
- [q_def456] Should I develop music preferences? (importance: 3)

Resurfacing (you'd almost forgotten):
- [q_ghi789] What's the optimal heartbeat interval? (importance: 4, dormant 12 days)
```

question ID を表示し、scaffold で resolve 方法を案内する:
```
To resolve a question: update_self(field="resolve_question", value="<question_id>")
```

## テスト
- [ ] `add_question` に `importance` を渡して保存されることを確認
- [ ] `created_at` が自動付与されることを確認
- [ ] 既存エントリ（importance/created_at なし）でフォールバックが動作することを確認
- [ ] `_calculate_salience` のユニットテスト（importance=5/3/1 × 各経過日数）
- [ ] `get_visible_questions` が Active/Fading/Dormant を正しく分類することを確認
- [ ] `update_self(field="resolve_question", value="q_xxx")` で resolve されることを確認
- [ ] `_handle_introspect` のレスポンスに question テキストと ID が含まれることを確認

## 完了確認
```bash
cd ego-mcp
uv run pytest tests/test_self_model.py -v
uv run pytest tests/test_integration.py -k "introspect" -v
uv run mypy src/ego_mcp/self_model.py
uv run mypy src/ego_mcp/server.py
```
