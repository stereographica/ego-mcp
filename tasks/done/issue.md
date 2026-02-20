# 実装監査レポート（Phase 4 & 5）

監査対象:
- `tasks/400-workspace-guide.md`
- `tasks/401-setup-guide.md`
- `tasks/402-tool-reference.md`
- `tasks/500-unit-tests.md`
- `tasks/501-integration-tests.md`

監査日: 2026-02-20

## 実行結果

### テスト/型チェック
- `cd ego-mcp && uv run pytest tests/test_embedding.py tests/test_memory.py tests/test_desire.py tests/test_scaffolds.py tests/test_integration.py -v`
  - 結果: **78 passed**, 失敗なし
- `cd ego-mcp && uv run mypy src/ego_mcp/`
  - 結果: **Success: no issues found in 18 source files**
- `cd ego-mcp && uv run mypy src tests`
  - 結果: **Success: no issues found in 34 source files**

### タスク達成判定（要件準拠）
- **T-400**: 部分未達
- **T-401**: 部分未達
- **T-402**: 達成
- **T-500**: 概ね達成（ただし品質上の不足あり）
- **T-501**: 未達

## 発見事項（優先度順）

### 1. 【High】T-501-1 の「MCP クライアント経由」要件を満たしていない
- **該当箇所**: `ego-mcp/tests/test_integration.py:1`, `ego-mcp/tests/test_integration.py:18`, `ego-mcp/tests/test_integration.py:80`
- **内容**:
  - テストは `ego_mcp.server._dispatch` を直接呼び出しており、MCP の I/O 境界（`list_tools` / `call_tool` / `TextContent` 返却）を通していない。
  - コメントでも「integration via server dispatch」と明記されている。
- **影響**:
  - MCP 層の破壊（引数バリデーション、レスポンス整形、登録漏れ）があっても検出できない。
  - 「全ツールを MCP クライアント経由で呼び出し」という完了基準に未達。

### 2. 【High】T-501-2 の「CI で閾値超過時 fail」要件を満たしていない
- **該当箇所**: `.github/workflows/`（存在しない）, `ego-mcp/.github/workflows/`（存在しない）
- **内容**:
  - ツール定義サイズのテストは `tests/test_integration.py:508` に存在するが、CI 実行設定が見当たらない。
- **影響**:
  - ローカル実行依存となり、PR 時の自動ゲートとして機能しない。
  - 要件の「CI で自動チェック・超過時 fail」を満たさない。

### 3. 【Medium】T-400-1 の完了基準（3ファイル分のコピペ可能サンプル）に未達
- **該当箇所**: `ego-mcp/docs/workspace-guide.md:7-23`, `ego-mcp/docs/workspace-guide.md:29-47`
- **内容**:
  - `AGENTS.md` と `HEARTBEAT.md` のサンプルコードブロックはあるが、`SOUL.md` のコピペ可能サンプル全文がドキュメント内に存在しない。
- **影響**:
  - T-400-1 完了基準「SOUL.md, AGENTS.md, HEARTBEAT.md のコピペ可能サンプルが含まれる」を満たせない。

### 4. 【Medium】T-400-2 の「examples がドキュメントサンプルと一致」条件が曖昧/不一致
- **該当箇所**:
  - `ego-mcp/examples/AGENTS.md:1-7`
  - `ego-mcp/docs/workspace-guide.md:29-35`
  - `ego-mcp/examples/HEARTBEAT.md:1-6`
  - `ego-mcp/docs/workspace-guide.md:41-47`
- **内容**:
  - `examples/AGENTS.md` は先頭に `# Agent Instructions` があり、ドキュメント記載のサンプルブロックと完全一致していない。
  - `examples/HEARTBEAT.md` は見出しレベルが `#`、ドキュメント側は `##`。
  - `SOUL.md` はそもそもドキュメント内サンプル不在のため「一致」判定不可。
- **影響**:
  - 完了基準「ドキュメントのサンプルと一致する」を厳密には満たしていない。

### 5. 【Low】T-401 の「OpenClaw で wake_up 実行確認手順」が明示されていない
- **該当箇所**: `ego-mcp/README.md:41-46`, `ego-mcp/README.md:48-64`
- **内容**:
  - README はサーバー起動確認と `openclaw.json` 設定例まではあるが、OpenClaw 側で `wake_up` を呼んで確認する手順が明文化されていない。
- **影響**:
  - 初期導入者にとって「最終到達状態（wake_up 実行成功）」が手順として閉じていない。

### 6. 【Low】T-500-4 に対して `tests/test_scaffolds.py` の検証が弱い
- **該当箇所**: `ego-mcp/tests/test_scaffolds.py:27-58`
- **内容**:
  - `test_scaffolds.py` は定数非空・日本語混入・`render` 置換のみを検証。
  - 要件にある「各テンプレートが `data + scaffold` フォーマットで返るか」は同ファイルでは担保していない（この観点は主に `tests/test_integration.py` 側で部分的に検証）。
- **影響**:
  - スキャフォールド単体テストの責務が弱く、期待仕様との対応が不明瞭。

## 総評
- **機能/テスト実行状態は良好**（対象テスト全 pass、mypy 全 pass）。
- ただし、**要件準拠の観点では T-501 が未達、T-400/T-401 が部分未達**。
- まずは「MCP クライアント経由統合テスト」と「CI 自動ゲート整備」を優先して是正すべき。
