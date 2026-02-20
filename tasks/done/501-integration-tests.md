# 501: 結合テスト

## 目的
MCP サーバーとしてのツール連携を検証し、運用時のフローとツール定義品質を担保する。

## 前提
- 105 完了済み
- 500 の主要ユニットテストが通過していること

## 参照
- `design/tasks.md` の T-501

## 仕様

### T-501-1: MCP サーバーの結合テスト
- MCP クライアント経由で全ツールを呼び出す
- セッション開始フローを検証:
  - `wake_up` → `introspect` → `remember`
- Heartbeat フローを検証:
  - `feel_desires` → `introspect` → `remember`

### T-501-2: ツール定義のトークン数テスト
- `list_tools` レスポンスサイズを自動チェック
- 閾値超過時に CI が fail するテストを用意

## 完了確認
```bash
cd ego-mcp
uv run pytest tests/test_integration.py -v
```
