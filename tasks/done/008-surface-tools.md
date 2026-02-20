# 008: 表面ツール7個の実装

## 目的
LLM に常時公開する7つの MCP ツールを `server.py` に実装する。

## 前提
- 005（MemoryStore）、006（DesireEngine）、007（scaffolds）完了済み

## 参照
- `design/tool-design.md`「ツールカタログ」のレスポンス例（全て英語）

## 仕様

以下の7ツールを `server.py` の `@server.list_tools()` / `@server.call_tool()` に登録。

### 1. `wake_up` — セッション開始時
- 引数: なし
- 処理: 最新の introspection 記憶1件 + 欲求サマリ + 関係性サマリ（未実装時は "No relationship data yet."）
- 末尾に `SCAFFOLD_WAKE_UP` を付加
- 記憶なしの場合: `"No introspection yet."`

### 2. `feel_desires` — 欲求確認
- 引数: なし
- 処理: `DesireEngine.compute_levels()` → `format_summary()`
- 末尾に `SCAFFOLD_FEEL_DESIRES` を付加

### 3. `introspect` — 内省
- 引数: なし
- 処理: 直近記憶3件（1行サマリ × 3）+ 欲求サマリ + 自己モデルの未解決の問い（未実装時は空）
- 末尾に `SCAFFOLD_INTROSPECT` を付加

### 4. `consider_them` — ToM
- 引数: `person`（optional, default=config.companion_name）
- 処理: 関係性モデルから対話パターンサマリ（未実装時は "Not enough data yet."）
- 末尾に `SCAFFOLD_CONSIDER_THEM` を付加

### 5. `remember` — 記憶保存
- 引数: `content`(str必須), `emotion`(default:"neutral"), `importance`(default:3), `category`(default:"daily"), `valence`(default:0.0), `arousal`(default:0.5)
- 処理: `MemoryStore.save_with_auto_link()`
- レスポンス: `"Saved (id: xxx). Linked to N existing memories."`

### 6. `recall` — 記憶想起
- 引数: `context`(str必須), `n_results`(default:3), `emotion_filter`(optional), `category_filter`(optional)
- 処理: `MemoryStore.recall()` → 1行サマリ × N
- 末尾に `SCAFFOLD_RECALL` を付加

### 7. `am_i_being_genuine` — 本心チェック
- 引数: なし
- 処理: `SCAFFOLD_AM_I_GENUINE` をそのまま返す

## 全ツール共通ルール
- レスポンスは全て **英語**
- データ部と scaffold 部の間に `"---"` を挟む
- description はツール1個あたり1-2行に収める

## テスト
- 各ツールが MCP の `call_tool` で呼び出し可能
- レスポンスに scaffold テキストが含まれる
- remember → recall で保存した記憶が見つかる

## 完了確認
```bash
pytest tests/test_tools.py -v  # 全 pass
```
