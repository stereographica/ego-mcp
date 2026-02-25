# ego-mcp タスクリスト

> 本タスクリストは [idea.md](../idea.md) および [design/tool-design.md](./tool-design.md) に基づく。
> 各タスクは判断不要で実行可能な粒度に分解されている。

---

## フェーズ 0, 1

`tasks` ディレクトリにタスク化済み

## フェーズ 2: P1 拡張機能

`tasks` ディレクトリにタスク化済み

---

## フェーズ 3a: P2 追加機能

`tasks` ディレクトリにタスク化済み（300〜303）

---

## フェーズ 3b: 記憶・感情・忘却拡張

> 設計書: [idea.md](./idea.md) / [tool-design.md](./tool-design.md)

`tasks` ディレクトリにタスク化済み（600〜605）

| タスク | 概要 | 依存 |
|---|---|---|
| 600 | Emotion enum 拡張 + EMOTION_BOOST_MAP | なし |
| 601 | remember リンク記憶の可視化 | なし |
| 602 | recall フィルタ強化 + search_memories 廃止 | 601 |
| 603 | 未解決の問い: 解決・重要度・忘却 | なし |
| 604 | emotion_trend バックエンドツール新設 | 600 |
| 605 | 忘却と欲求の連動 | 601, 603 |

---

## フェーズ 6: 欲求システム・リバランス

> 設計書: [desire-system-rebalance.md](./desire-system-rebalance.md)

`tasks` ディレクトリにタスク化済み（700〜704）

| タスク | 概要 | 依存 |
|---|---|---|
| 700 | マイグレーションフレームワーク | なし |
| 701 | satisfaction_hours 調整 + マイグレーション | 700 |
| 702 | 暗黙の充足（Implicit Satisfaction） | 701 |
| 703 | feel_desires スキャフォールド改善 | 702 |
| 704 | バージョニングとリリースワークフロー | 700〜703 |

---

## フェーズ 7: 記憶重複防止・統合

> 設計書: [memory-dedup-design.md](./memory-dedup-design.md)

`tasks` ディレクトリにタスク化済み（800〜803）

| タスク | 概要 | 依存 |
|---|---|---|
| 800 | remember 保存前の重複検出ガード | なし |
| 801 | consolidate でのマージ候補検出 | 800 |
| 802 | スキャフォールドへの重複意識の追加 | 800 |
| 803 | バージョンアップと CI 全チェック | 800〜802 |

---

## フェーズ 8: forget ツール

> 設計書: [forget-tool-design.md](./forget-tool-design.md)

`tasks` ディレクトリにタスク化済み（900〜904）

| タスク | 概要 | 依存 |
|---|---|---|
| 900 | MemoryStore.delete メソッドの追加 | なし |
| 901 | Workspace Sync のエントリ除去 | 900 |
| 902 | forget ツールの追加 | 900, 901 |
| 903 | スキャフォールド改善とドキュメント更新 | 902 |
| 904 | バージョンアップと CI 全チェック | 900〜903 |

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

T-600 (Emotion拡張) ──────────────────→ T-604 (emotion_trend)

T-601 (remember可視化) ──→ T-602 (recall統合)
                        ──→ T-605 (忘却×欲求)

T-603 (問いのライフサイクル) ──→ T-605 (忘却×欲求)

T-105 ─→ T-400 (ドキュメント。サーバーが動く状態で書く)
T-400 ─→ T-401, T-402

T-100〜T-105 ─→ T-500 (テストはコード実装と並行可)
T-105 ─→ T-501

T-700 (マイグレーション基盤) ──→ T-701 (satisfaction_hours)
T-701 ──→ T-702 (暗黙の充足)
T-702 ──→ T-703 (スキャフォールド)
T-700〜703 ──→ T-704 (リリースワークフロー)
```
