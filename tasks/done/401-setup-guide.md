# 401: セットアップガイド

## 目的
ゼロからセットアップし、OpenClaw から `wake_up` を呼び出せる状態までの手順を明文化する。

## 前提
- 400 完了済み

## 参照
- `design/tasks.md` の T-401

## 成果物

`ego-mcp/README.md`:

- **プロジェクト概要**
- **インストール手順**
- **環境変数の設定方法**
  - Embedding プロバイダー（Gemini / OpenAI）の選択手順を含む
- **OpenClaw との接続方法**
  - `openclaw.json` の MCP 設定例を含む
- **動作確認手順**
  - `python -m ego_mcp` 起動確認
  - OpenClaw から `wake_up` 実行確認

## 完了確認
- README の手順だけでセットアップから OpenClaw 接続まで再現できる
- `wake_up` 実行確認までの手順が欠けなく記載されている
