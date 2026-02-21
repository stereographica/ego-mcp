# ego-mcp private memory（秘密のメモ）統合設計

## 0. 目的

`remember` に `private` フラグを導入し、AI エージェントが「外に出さない前提の記憶」を自然に扱えるようにする。  
同時に、`private` 記憶が workspace ファイルや実行ログに漏れないことを保証する。

## 1. 背景と設計判断

会話で合意した方針は以下。

1. 「秘密のメモを使える」ことはセッション開始時に意識に上げる  
2. 保存時に `remember(private=true)` を選べるようにする  
3. `recall` は private 記憶も通常の記憶と同様に検索対象に含める  
4. `recall` 結果には各記憶の `private` メタデータを含める（判断材料）  
5. `private` 記憶は workspace sync しない  
6. `private` 記憶の内容はログ出力しない

この方針に基づき、秘密性の担保は「検索から除外する」ではなく「外部出力経路を制御する」で実現する。

## 2. スコープ

対象:

1. `remember` 入力スキーマ拡張
2. 記憶データモデル拡張（private 属性）
3. workspace sync 抑止
4. ログの redaction
5. セッション開始時スキャフォールド更新（private 記憶の存在を想起）

非対象:

1. private 記憶の暗号化 at-rest
2. `recall` 結果の強制マスキング
3. ポリシーエンジンによる会話出力制御

## 3. 機能要件

### FR-1 `remember` private フラグ

1. `remember` に `private: boolean` を追加する
2. 省略時は `false`（既存互換）
3. `private=true` で保存された記憶は `is_private=true` として永続化する

### FR-2 workspace 出力抑止

1. `private=true` の記憶は `WorkspaceMemorySync.sync_memory()` を呼ばない
2. `memory/YYYY-MM-DD.md` と `MEMORY.md` と `inner-monologue-latest.md` に書き出さない

### FR-3 ログ抑止

1. `private=true` の `remember` 呼び出しでは、ログに記憶本文を残さない
2. `Tool invocation` / `Routing tool call` / 例外ログのすべてで同一 redaction を適用する

### FR-4 recall 方針

1. `recall` と `search_memories` は private/public を区別せず検索する（デフォルト挙動）
2. `recall` と `search_memories` の各結果に `private: true|false` を明示する
3. 既存の検索品質（semantic + Hopfield）を維持する

### FR-5 セッション開始時の想起

1. `wake_up` 系のスキャフォールドに「private 記憶を使える」短い案内を追加する
2. 案内は「選択肢の提示」に留め、使い方を指示しない
3. 長文化せず、トークンコストを抑える

## 4. データモデル設計

### 4.1 型

`Memory` に以下を追加する。

1. `is_private: bool = False`

### 4.2 永続化メタデータ（Chroma）

保存メタデータに以下を追加する。

1. `is_private`: `1/0` もしくは `true/false`（実装で一貫した表現を採用）

読み込み時は後方互換を維持する。

1. `is_private` が未存在なら `False`
2. 文字列/数値/真偽値の揺れを吸収して bool に正規化

## 5. ツール仕様変更

### 5.1 remember

入力追加:

```json
{
  "private": {
    "type": "boolean",
    "default": false,
    "description": "When true, keep this memory internal and skip workspace sync."
  }
}
```

処理:

1. `private` を `is_private` として保存
2. `is_private=true` の場合は workspace sync をスキップ
3. レスポンス文言は既存互換を優先しつつ、必要なら private 保存を明示する短い追記を検討

### 5.2 recall / search_memories

入力変更なし（本設計では追加パラメータ不要）。

1. 内部検索は private を含めて実行
2. 各結果行に `private: true|false` を常に付与する
3. `private: true` は「口外可否を判断するための内部メタデータ」として扱う

レスポンス例:

```text
2 related memories:
1. [2026-02-21] I felt conflicted... (emotion: sad, private: true)
2. [2026-02-20] Shared a technical win... (emotion: happy, private: false)
```

## 6. ログ設計（Redaction）

`server.call_tool()` と `_dispatch()` で使う `tool_args` は、生引数を直接ログしない。  
専用サニタイザを経由する。

### 6.1 サニタイズ規則

`name == "remember"` かつ `private == true` の場合:

1. `content` は必ず `"[REDACTED_PRIVATE_MEMORY]"` に置換
2. 任意で以下も最小化する  
`secondary`, `body_state`, `tags` など自由記述が混ざるフィールド
3. 代わりに `content_length`, `private=true`, `category`, `importance` など非機微メタ情報を残す

それ以外は既存挙動を維持。

## 7. wake_up スキャフォールド

`SCAFFOLD_WAKE_UP` に短い1行を追加する。

推奨文言（さりげない想起）:

`If something is hard to say yet, you can keep it with remember(private=true).`

補足文言（必要時のみ）:

`Private memories stay internal and are not synced to workspace logs.`

禁止事項:

1. 「こういう時は private を使うべき」といった行動指示
2. wake_up を説明モードにする長文ガイド

## 8. 変更対象（実装ガイド）

想定変更ファイル:

1. `ego-mcp/src/ego_mcp/server.py`
2. `ego-mcp/src/ego_mcp/memory.py`
3. `ego-mcp/src/ego_mcp/types.py`
4. `ego-mcp/src/ego_mcp/scaffolds.py`
5. `ego-mcp/src/ego_mcp/workspace_sync.py`（必要なら防御的チェック追加）
6. `ego-mcp/tests/test_integration.py`
7. `ego-mcp/tests/test_memory.py`
8. `ego-mcp/tests/test_scaffolds.py`
9. `ego-mcp/tests/test_logging_utils.py` または `server` 周辺ログ検証テスト
10. `ego-mcp/docs/tool-reference.md`

## 9. テスト設計

### 9.1 remember private 保存

1. `remember(private=true)` 後に `is_private=True` で保存される
2. `remember(private=false)` 既存挙動が壊れない

### 9.2 workspace sync 抑止

1. private 記憶保存後に `memory/*.md`、`MEMORY.md`、`inner-monologue-latest.md` が更新されない
2. public 記憶は従来どおり同期される

### 9.3 ログ redaction

1. private `remember` 実行時、ログに本文が含まれない
2. 非 private 記憶のログ挙動は現行互換

### 9.4 recall 挙動

1. private 記憶を保存後、通常 `recall` で関連結果に出る
2. 結果行に `private: true|false` が必ず含まれる
3. private/public 混在時でも検索件数や並びが不自然に崩れない

### 9.5 wake_up 誘導

1. スキャフォールドに private 記憶案内文が含まれる
2. 文言が「選択肢の提示」であり、使用タイミングを指示しない

## 10. リスクと対策

1. ログ漏れリスク  
対策: ログ地点を一箇所に集約し、必ずサニタイザを通す

2. 既存データ互換性  
対策: `is_private` 未設定時は `False` 扱い

3. private 情報の会話露出  
対策: 本設計ではツール層で強制しない（エージェント判断）。将来的に出力ポリシー層を別設計で追加可能

## 11. 段階的導入

1. Step 1: データモデルと `remember` スキーマ拡張
2. Step 2: workspace sync 抑止
3. Step 3: ログ redaction
4. Step 4: wake_up スキャフォールド更新
5. Step 5: テスト・ドキュメント更新
