# 012: README + セットアップガイド

## 目的
ゼロからセットアップ → OpenClaw で動作するまでの手順を書く。

## 前提
- 010, 011 完了済み

## 成果物

`ego-mcp/README.md`:

- **概要**: ego-mcp とは何か（認知スキャフォールドMCP。1段落）
- **特徴**: 表面7ツール、段階的開示、レスポンス全英語、etc.
- **クイックスタート**:
  1. `pip install -e .`
  2. 環境変数設定（`GEMINI_API_KEY` or `OPENAI_API_KEY`）
  3. `python -m ego_mcp` で起動確認
- **OpenClaw との接続**: `openclaw.json` の MCP 設定例
  ```json
  {
    "mcpServers": {
      "ego": {
        "command": "python",
        "args": ["-m", "ego_mcp"],
        "env": { "GEMINI_API_KEY": "..." }
      }
    }
  }
  ```
- **環境変数一覧**: 全環境変数をテーブルで
- **ツール一覧**: 表面7 + バックエンド8 の1行サマリテーブル
- **workspace ガイドへのリンク**: `docs/workspace-guide.md`

## 完了確認
- README.md が存在し、上記セクションが全て含まれる
- OpenClaw 設定例がコピペ可能
