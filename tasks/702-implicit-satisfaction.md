# 702: 暗黙の充足（Implicit Satisfaction）

## 目的
ツール使用に連動して関連する欲求を自動的に部分充足する仕組みを導入する。これにより、セッション中に欲求間の差が生まれ、欲求に基づく行動選択が機能するようになる。

## 前提
- 701（satisfaction_hours 調整）が完了していること

## 参照
- `design/desire-system-rebalance.md` §A

## タスク

### T-702-1: 暗黙の充足マッピングと `satisfy_implicit` メソッドの追加
対象ファイル: `src/ego_mcp/desire.py`

モジュールレベルに暗黙の充足マッピングを定義する:

| ツール | 充足する欲求 | quality |
|--------|-------------|---------|
| `remember` | `expression` | 0.3 |
| `recall` | `information_hunger` | 0.3 |
| `recall` | `curiosity` | 0.2 |
| `introspect` | `cognitive_coherence` | 0.3 |
| `introspect` | `pattern_seeking` | 0.2 |
| `consider_them` | `social_thirst` | 0.4 |
| `consider_them` | `resonance` | 0.3 |
| `emotion_trend` | `pattern_seeking` | 0.3 |
| `consolidate` | `cognitive_coherence` | 0.3 |
| `update_self` | `cognitive_coherence` | 0.3 |
| `update_relationship` | `social_thirst` | 0.2 |

`remember` でカテゴリが `introspection` の場合は、上記に加えて `cognitive_coherence` を quality=0.4 で充足する。

`DesireEngine` に以下のメソッドを追加する:

**`satisfy_implicit(self, tool_name: str, category: str | None = None) -> None`:**
- マッピング辞書から `tool_name` に対応するエントリを取得する
- `tool_name == "remember"` かつ `category == "introspection"` の場合、`cognitive_coherence` の追加充足をマッピングの先頭に追加する
- 各エントリに対して既存の `self.satisfy(desire_name, quality)` を呼ぶ
- マッピングに存在しない `tool_name` は何もせず return する

マッピングしないツール: `wake_up`, `feel_desires`, `am_i_being_genuine`（観測・姿勢ツールであり、欲求に関連する活動ではない）, `satisfy_desire`（明示的な充足。暗黙の充足と役割が異なる）

### T-702-2: サーバーハンドラに暗黙の充足呼び出しを追加
対象ファイル: `src/ego_mcp/server.py`

`call_tool` ハンドラ内で、マッピング対象のツールの処理完了後に `desire.satisfy_implicit(tool_name, ...)` を呼び出す。

**`remember` の場合のみ `category` 引数を渡す:**
```python
elif name == "remember":
    result = await _handle_remember(memory, args)
    desire.satisfy_implicit("remember", category=args.get("category"))
    return result
```

その他のマッピング対象ツール（`recall`, `introspect`, `consider_them`, `emotion_trend`, `consolidate`, `update_self`, `update_relationship`）はツール名のみで呼び出す:
```python
desire.satisfy_implicit(name)
```

`desire` の取得は既存の `_desire` グローバル変数を使う（`init_server()` で初期化済み）。

### T-702-3: テスト
対象ファイル: `tests/test_desire.py`, `tests/test_server.py`

**`test_desire.py` に追加:**
- `satisfy_implicit("recall")` で `information_hunger` と `curiosity` の `last_satisfied` が更新されること
- `satisfy_implicit("remember", category="introspection")` で `cognitive_coherence`（quality=0.4）と `expression`（quality=0.3）の両方が充足されること
- `satisfy_implicit("wake_up")` で何も変更されないこと（マッピング対象外）
- 暗黙の充足の quality（0.2〜0.4）が明示的な `satisfy()` のデフォルト quality（0.7）より低いこと

**`test_server.py` に追加:**
- `remember` ツール呼び出し後に `expression` 欲求のレベルが低下していること
- `consider_them` ツール呼び出し後に `social_thirst` 欲求のレベルが低下していること

## 完了確認
```bash
cd ego-mcp
GEMINI_API_KEY=test-key uv run pytest tests/test_desire.py tests/test_server.py -v
uv run mypy src/ego_mcp/desire.py src/ego_mcp/server.py
```
