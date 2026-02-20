# ego-mcp タスクリスト

> 本タスクリストは [idea.md](../idea.md) および [design/tool-design.md](./tool-design.md) に基づく。
> 各タスクは判断不要で実行可能な粒度に分解されている。

---

## フェーズ 0, 1

`tasks` ディレクトリにタスク化済み

## フェーズ 2: P1 拡張機能

`tasks` ディレクトリにタスク化済み

---

## フェーズ 3: P2 追加機能

`tasks` ディレクトリにタスク化済み

---

## フェーズ 4: ドキュメント

### T-400: OpenClaw workspace ガイド

- [ ] **T-400-1** `docs/workspace-guide.md` を作成する
  - ego-mcp 導入時の OpenClaw workspace ファイルの書き方ガイド
  - 以下のセクションを含む:
    - **SOUL.md に書くべきこと / 書かないこと**
      - ✅ 書く: 一人称、口調、コアバリュー、絶対原則、感情の表現方針
      - ❌ 書かない: 欲求の扱い方（ツールレスポンスに移管済み）、思考方法の詳細指示
      - サンプル全文を提供
    - **AGENTS.md に書くべきこと（4行版）**
      - セッション開始時: `wake_up` → `introspect` → 内省を `remember` で保存
      - Heartbeat 時: `feel_desires` → 必要なら `introspect` → 行動 or HEARTBEAT_OK
      - 返答前: `consider_them` → 必要なら `am_i_being_genuine`
      - 重要な体験の後: `remember` で保存
      - サンプル全文を提供
    - **HEARTBEAT.md に書くべきこと**
      - サンプル全文を提供
    - **IDENTITY.md / USER.md**
      - ego-mcp 固有の追記事項（あれば）
    - **やってはいけないこと**
      - SOUL.md にツール名を書かない
      - AGENTS.md に思考方法の詳細を書かない
      - skills/ に長いワークフローを書かない
  - **完了基準:** ドキュメントに SOUL.md, AGENTS.md, HEARTBEAT.md のコピペ可能なサンプルが含まれる。「書くべきこと/書かないこと」が明確に分離されている

- [ ] **T-400-2** 各サンプルファイルを `examples/` に作成する
  - `examples/SOUL.md` — サンプル SOUL.md（コピペ可能）
  - `examples/AGENTS.md` — サンプル AGENTS.md（4行版）
  - `examples/HEARTBEAT.md` — サンプル HEARTBEAT.md
  - **完了基準:** 各ファイルが存在し、ドキュメントのサンプルと一致する

### T-401: セットアップガイド

- [ ] **T-401-1** `README.md` を作成する
  - プロジェクト概要
  - インストール手順
  - 環境変数の設定方法（Embedding プロバイダーの選び方を含む）
  - OpenClaw との接続方法（`openclaw.json` の MCP 設定例）
  - 動作確認手順
  - **完了基準:** README に従って、ゼロからセットアップ → OpenClaw で `wake_up` が呼べる状態になる手順が書かれている

### T-402: ツールリファレンス

- [ ] **T-402-1** `docs/tool-reference.md` を作成する
  - 全15ツールのリファレンス
  - 各ツール: 名前、説明文、inputSchema、レスポンス例、呼ぶタイミング
  - **完了基準:** 全ツールが漏れなく記載されている

---

## フェーズ 5: テスト・品質

### T-500: ユニットテスト

- [ ] **T-500-1** Embedding プロバイダーのテスト
  - Gemini / OpenAI のモック
  - バッチ Embedding のテスト
  - エラー時のリトライテスト
  - **完了基準:** `pytest tests/test_embedding.py` が全て pass

- [ ] **T-500-2** MemoryStore のテスト
  - save / search / recall / list_recent / auto_link
  - 感情トレース付き保存・検索
  - **完了基準:** `pytest tests/test_memory.py` が全て pass

- [ ] **T-500-3** DesireEngine のテスト
  - compute_levels / satisfy / boost / format_summary
  - シグモイド計算の正確性（特定時間経過後の期待値）
  - **完了基準:** `pytest tests/test_desire.py` が全て pass

- [ ] **T-500-4** スキャフォールドのテスト
  - 各テンプレートが正しいフォーマット（data + scaffold）で返るか
  - companion_name の置換が動作するか
  - **完了基準:** `pytest tests/test_scaffolds.py` が全て pass

### T-501: 結合テスト

- [ ] **T-501-1** MCP サーバーの結合テスト
  - MCP クライアント経由で全ツールを呼び出し
  - セッション開始フロー: `wake_up` → `introspect` → `remember`
  - Heartbeat フロー: `feel_desires` → `introspect` → `remember`
  - **完了基準:** `pytest tests/test_integration.py` が全て pass

- [ ] **T-501-2** ツール定義のトークン数テスト
  - `list_tools` のレスポンスサイズが目標値以下であることを自動チェック
  - **完了基準:** CI で自動チェックされ、閾値超過時に fail する

---

## 依存関係

```
T-000 ─→ T-001 ─→ T-002 ─→ T-100 ─→ T-103-5 (remember)
                                    ─→ T-103-6 (recall)
                         ─→ T-101 ─→ T-103-2 (feel_desires)
                         ─→ T-102 ─→ T-103-1 (wake_up)
                                   ─→ T-103-3 (introspect)
                                   ─→ T-103-4 (consider_them)
                                   ─→ T-103-7 (am_i_being_genuine)

T-103-* ─→ T-104-* ─→ T-105 (サーバー結合)

T-105 ─→ T-200 (関係性モデル)
      ─→ T-201 (自己モデル)
      ─→ T-202 (感情記憶)

T-200, T-201 ─→ T-300, T-301, T-302, T-303

T-105 ─→ T-400 (ドキュメント。サーバーが動く状態で書く)
T-400 ─→ T-401, T-402

T-100〜T-105 ─→ T-500 (テストはコード実装と並行可)
T-105 ─→ T-501
```
