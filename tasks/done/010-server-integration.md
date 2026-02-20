# 010: MCP サーバー結合 + トークン計測

## 目的
全ツール（表面7 + バックエンド8）を統合し、server.py を完成させる。ツール定義のトークン消費量を検証する。

## 前提
- 008, 009 完了済み

## 仕様

### server.py の仕上げ
- `server.py` で全依存の初期化:
  - `EgoConfig.from_env()` → `EmbeddingProvider` → `EgoEmbeddingFunction` → `MemoryStore`
  - `DesireEngine(config.data_dir / "desires.json")`
- `@server.list_tools()` に全15ツールを登録
- `@server.call_tool()` でディスパッチ

### トークン計測
- `list_tools` レスポンスをテキスト化し文字数を計測するスクリプト or テストを追加
- 目標: 合計 6,000文字以下（≈ 1,500 tokens）
- 超過時はバックエンドツールの description を短縮

## テスト（`tests/test_integration.py`）
- セッション開始フロー: `wake_up` → `introspect` → `remember`（content: 内省テキスト, category: introspection）
- Heartbeat フロー: `feel_desires` → `introspect` → `remember`
- ツール定義トークン数が閾値以下

## 完了確認
```bash
pytest tests/test_integration.py -v  # 全 pass
python -m ego_mcp                    # サーバー起動成功
```
