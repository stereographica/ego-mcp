# 011: OpenClaw workspace ガイド + サンプルファイル

## 目的
ego-mcp 導入時に SOUL.md, AGENTS.md 等をどう書くべきかのガイドとサンプルファイルを作成する。

## 前提
- 010 完了済み（ツールが動作する状態）

## 参照
- `idea.md` のスコープ分離表（各レイヤーの責務）
- `design/tool-design.md` の AGENTS.md 推奨版

## 成果物

### 1. `docs/workspace-guide.md`
以下のセクションを含むガイド:

- **SOUL.md に書くべきこと / 書かないこと**
  - ✅ 書く: 一人称、口調、コアバリュー、絶対原則、感情の表現方針
  - ❌ 書かない: ツール名、欲求の扱い方（→ ツールレスポンスに移管済み）、思考方法の詳細
- **AGENTS.md に書くべきこと（4行版）**
  - セッション開始: `wake_up` → `introspect` → `remember`
  - Heartbeat: `feel_desires` → 必要なら `introspect`
  - 返答前: `consider_them` → `am_i_being_genuine`
  - 重要体験後: `remember`
- **HEARTBEAT.md に書くべきこと**
- **アンチパターン集**
  - SOUL.md にツール名を書く ❌
  - AGENTS.md に思考の型を長々書く ❌
  - skills/ に長いワークフローを書く ❌

### 2. サンプルファイル
- `examples/SOUL.md` — テンプレート（ユーザーがカスタマイズする部分を `<!-- CUSTOMIZE -->` で明示）
- `examples/AGENTS.md` — 4行版
- `examples/HEARTBEAT.md`

## 完了確認
- `docs/workspace-guide.md` が存在し、上記セクションが全て含まれる
- `examples/` に3つのサンプルファイルが存在する
- サンプル AGENTS.md にツール名が正しく記載されている
