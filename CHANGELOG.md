# Changelog

ego-mcp のリリース履歴。

## [0.3.0] - 2026-03-01

### Fixed
- ego-mcp: `list_recent()` が ChromaDB の `get(limit=N)` の順序不定性により最新記憶を返さないバグを修正（全件取得→ソート→スライスに変更）
- ego-mcp: `list_episodes()` も同様に全件取得→ソート→スライスに修正
- ego-mcp: `EMOTION_DEFAULTS` に `"contentment"` / `"melancholy"` のエントリ追加（v0.2.0 での Emotion enum 追加時の漏れ）
- Dashboard `sql_store.py` の valence/arousal クエリに `::double precision` キャスト追加、Python 側の型チェックを `(int, float)` に統一

### Added
- Dashboard ログベースマイグレーションスクリプト（`scripts/migrate_emotion_telemetry.py`）— completion テレメトリの壊れた感情データを invocation ログから再構築

### Changed
- バージョンアップ: ego-mcp 0.2.9→0.3.0

## [0.2.9] - 2026-03-01

### Added
- ego-mcp: `_completion_log_context()` に Relationship テレメトリ出力を追加（`consider_them` / `wake_up` 完了時に `trust_level`, `total_interactions`, `shared_episodes_count` をログ extra に付与）
- Dashboard ingestor に Relationship データパース（構造化フィールド優先 + tool_output 正規表現フォールバック）
- Dashboard `current()` API に `latest_relationship` フィールド追加（in-memory / SQL 両対応）
- Dashboard Now タブに `RelationshipStatus` カード（trust バー + interactions + shared episodes）
- Dashboard Now タブに `CircumplexCard`（Valence-Arousal チャートを独立カードに分離・拡大表示）
- Dashboard History タブに `EmotionDistributionChart`（emotion 別集計棒グラフ）
- Dashboard `IntensityChart` ツールチップに emotion ラベルを表示
- Dashboard フロントエンド API に `fetchStringTimeline` / `fetchStringHeatmap` を追加

### Fixed
- Dashboard Activity Feed の `scrollIntoView` によるメインフレームスクロール問題を修正（viewport `scrollTop` に変更）
- Dashboard Activity Feed のモバイル幅崩れを修正（`overflow-hidden` + `flex-wrap`）

### Changed
- Dashboard Now タブを 2 カラムグリッドにレイアウト再構築（EmotionStatus / RelationshipStatus / DesireRadar / CircumplexCard / ActivityFeed / AnomalyAlerts）
- Dashboard `EmotionStatus` から `CircumplexChart` を分離
- Dashboard `websockets` 依存を明示化（既存 WebSocket エンドポイント用）
- バージョンアップ: ego-mcp 0.2.8→0.2.9, dashboard 0.1.0→0.2.0

## [0.2.8] - 2026-03-01

### Fixed
- Dashboard ingestor が全ツールの完了ログから感情データを取り込むように修正
- Dashboard Activity feed の WebSocket レースコンディションを修正（StrictMode 二重マウント対応）

### Added
- 感情ラベルから intensity / valence / arousal への自動マッピング（`EMOTION_DEFAULTS`）

### Changed
- Dashboard Live tail のロガーフィルターをコンテンツ検索に置き換え
- Dashboard Emotional state に Valence / Arousal のラッセル円環モデル表示を追加

## [0.2.7] - 2026-02-28

### Fixed
- `update_relationship` にフィールド名バリデーションを追加し、不正フィールド更新をエラーメッセージで返すように変更
- `update_relationship` のエイリアス解決を追加（`trust` → `trust_level`、`facts` → `known_facts` など）
- `update_relationship(field="dominant_tone")` が `emotional_baseline` を通じて永続化されるように修正
- Dashboard Now タブの Emotional state が最新の感情イベント（`latest_emotion`）を表示するように修正
- Dashboard Activity feed が WebSocket 未接続時でも HTTP ポーリングでログを表示するように修正

### Added
- `remember` に `shared_with` / `related_memories` パラメータを追加
- `remember(shared_with=...)` 実行時に shared episode を自動作成し、relationship の `shared_episode_ids` に連携

### Changed
- Dashboard SessionSummary から `latest latency` パネルを削除し、Now タブのサマリーを 2 カラム表示に変更
- `server.py` / `memory.py` をモジュール分割しリファクタリング（public API に変更なし）

## [0.2.6] - 2026-02-28

### Removed
- `MEMORY.md` への自動書き込み — `WorkspaceMemorySync._append_curated()` メソッド、`CURATION_CATEGORIES` 定数、`SyncResult.curated_updated` フィールドを削除
- `forget` 実行時の `MEMORY.md` エントリ除去処理

### Changed
- `remember` のワークスペース同期を `memory/YYYY-MM-DD.md` と `memory/inner-monologue-latest.md` のみに限定
- `docs/workspace-guide.md` に手動キュレーション推奨ワークフローを追記
- `docs/tool-reference.md` の `remember` / `forget` 説明にワークスペース同期の挙動を明記

### Design
- `design/wip/workspace-memory-curation-design.md` — ワークスペース記憶同期の整理設計書

## [0.2.4] - 2026-02-25

### Changed
- `IMPLICIT_SATISFACTION_MAP` に `wake_up` エントリ追加（`predictability` 0.05）
- `introspect` / `consider_them` の暗黙充足に `predictability` 0.1 を追加
- `wake_up` ルーティングで `satisfy_implicit("wake_up")` を呼び出すように変更
- `SCAFFOLD_FEEL_DESIRES` に予測検証の促し文言を追加
- `SCAFFOLD_INTROSPECT` に予測の振り返り文言を追加
- `SCAFFOLD_CONSIDER_THEM` に予測確認の文言を追加


## [0.2.3] - 2026-02-25

### Added
- `forget` ツール（記憶 ID 指定削除）
- `MemoryStore.delete` メソッド（双方向リンクの逆リンククリーンアップ付き）
- `WorkspaceMemorySync.remove_memory` メソッド（同期済み Markdown エントリ除去）

### Changed
- `consolidate` のマージ候補スキャフォールドに `forget` への導線を追加
- `get_episode` で削除済み `memory_ids` をフィルタし、欠損数を注記
- `docs/tool-reference.md` / `README.md` のツール一覧・フローを更新

### Design
- `design/forget-tool-design.md` — forget ツール設計書


## [0.2.2] - 2026-02-25

### Added
- `remember` 実行時の保存前重複検出ガード — コサイン距離 0.05 未満（similarity 0.95 以上）の既存記憶がある場合、保存をブロックし既存記憶の情報を返す
- `consolidate` 実行時のマージ候補検出 — コサイン距離 0.10 未満の類似記憶ペアを検出し、統合候補として提示
- `MergeCandidate` データクラス（consolidation.py）
- `ConsolidationStats` に `merge_candidates` フィールドを追加

### Changed
- `save_with_auto_link` の返り値を 3 要素から 4 要素タプルに拡張（`duplicate_of` を追加）
- `SCAFFOLD_INTROSPECT` の `remember` 誘導に新規性の自己評価を追加（`"If this is a genuinely new insight, save with remember"`）
- `_handle_consolidate` のレスポンスにマージ候補の表示を追加

### Design
- `design/memory-dedup-design.md` — 記憶重複防止・統合の設計書

## [0.2.1] - 2026-02-23

### Added
- 暗黙の充足（Implicit Satisfaction）— ツール使用に連動した自動的な部分充足
- `DesireEngine.satisfy_implicit` メソッド
- `IMPLICIT_SATISFACTION_MAP` — ツールと欲求の充足マッピング

### Changed
- 全 9 欲求の `satisfaction_hours` をリバランス（セッション間隔に合わせたスケール調整）
- `SCAFFOLD_FEEL_DESIRES` を認知の型に改善（行動指示から内的気づきへの転換）

### Infrastructure
- データファイルのマイグレーションフレームワーク（`ego_mcp.migrations`）
- `0002_desire_rebalance` マイグレーション — 全欲求の `last_satisfied` をリセット
- `CLAUDE.md` にリリースワークフローを追記

### Design
- `design/desire-system-rebalance.md` — 欲求システム・リバランスの設計書

## [0.2.0] - 2026-02-16

### Added
- Emotion enum に 4 値を追加（`melancholy`, `anxious`, `contentment`, `frustrated`）
- `recall` のフィルタ強化（`date_from`, `date_to`, `valence_range`, `arousal_range`）
- `remember` リンク記憶の可視化（上位 3 件の類似記憶を表示）
- `emotion_trend` ツール — 感情パターンの時系列分析
- 忘却と欲求の統合 — fading question が `cognitive_coherence` をブースト
- 問いかけライフサイクル管理（salience decay, band 分類）

### Changed
- `EMOTION_BOOST_MAP` に新 Emotion のエントリを追加
- `_derive_desire_modulation` に新 Emotion の判定ロジックを追加

## [0.1.0] - 2026-01-26

初回リリース。

### Added
- MCP サーバー基盤（`mcp` SDK 統合）
- 7 Surface Tools + 8 Backend Tools
- ChromaDB ベースの記憶ストア（embedding: Gemini / OpenAI）
- Hopfield ネットワークによる連想的記憶想起
- 欲求エンジン（9 欲求、シグモイド計算）
- 認知スキャフォールド（6 テンプレート）
- 自己モデル・関係性モデル
- エピソード記憶
- 記憶の統合（ConsolidationEngine）
- 連想エンジン（AssociationEngine）
- Workspace 同期（OpenClaw 連携）
