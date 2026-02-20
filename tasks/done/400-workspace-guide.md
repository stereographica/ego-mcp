# 400: OpenClaw workspace ガイド

## 目的
ego-mcp 導入時に、OpenClaw workspace ファイル（SOUL.md / AGENTS.md / HEARTBEAT.md）を正しく構成するためのガイドとサンプルを整備する。

## 前提
- 010 完了済み（MCP サーバーが動作していること）

## 参照
- `design/tasks.md` の T-400
- `design/tool-design.md` の AGENTS.md 推奨フロー

## 成果物

### 1. `ego-mcp/docs/workspace-guide.md`
以下のセクションを含む:

- **SOUL.md に書くべきこと / 書かないこと**
  - ✅ 書く: 一人称、口調、コアバリュー、絶対原則、感情の表現方針
  - ❌ 書かない: 欲求の扱い方（ツールレスポンスに移管済み）、思考方法の詳細指示
  - コピペ可能なサンプル全文を含める
- **AGENTS.md に書くべきこと（4行版）**
  - セッション開始時: `wake_up` → `introspect` → `remember`
  - Heartbeat 時: `feel_desires` → 必要なら `introspect` → 行動 or `HEARTBEAT_OK`
  - 返答前: `consider_them` → 必要なら `am_i_being_genuine`
  - 重要な体験の後: `remember`
  - コピペ可能なサンプル全文を含める
- **HEARTBEAT.md に書くべきこと**
  - コピペ可能なサンプル全文を含める
- **IDENTITY.md / USER.md**
  - ego-mcp 固有の追記事項（必要なら）
- **やってはいけないこと**
  - SOUL.md にツール名を書かない
  - AGENTS.md に思考方法の詳細を書かない
  - skills/ に長いワークフローを書かない

### 2. `ego-mcp/examples/` のサンプルファイル
- `ego-mcp/examples/SOUL.md`
- `ego-mcp/examples/AGENTS.md`
- `ego-mcp/examples/HEARTBEAT.md`

## 完了確認
- `ego-mcp/docs/workspace-guide.md` に SOUL.md / AGENTS.md / HEARTBEAT.md のコピペ可能サンプルが含まれる
- 「書くべきこと / 書かないこと」が明確に分離されている
- `ego-mcp/examples/` の3ファイルが存在し、ガイド内サンプルと一致する
