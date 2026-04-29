# Changelog

ego-mcp / dashboard のリリース履歴。

## [1.1.0] - 2026-04-29

### Added
- ego-mcp: Person network — `Memory.involved_person_ids` を追加し、`shared_episode_ids` との双方向ポインタを確立。`remember(shared_with=...)` で resolved person id をメモリ側にも記録するようにした
- ego-mcp: `RelationshipModel` に `aliases` (list[str]) と `relation_kind` (`"interlocutor"` / `"mentioned"`) を追加。`RelationshipStore.resolve_person()` が canonical id とエイリアスの完全一致解決を行い、`consider_them` / `attune` / `update_relationship` / `remember(shared_with=...)` から再利用される
- ego-mcp: `recall` が `RecalledPerson` を最大3名まで surface する2経路を追加 — `[resonance]` は返却メモリの `involved_person_ids` を頻度+最近性でランクし、`[involuntary]` は `PROUST_PERSON_PROBABILITY ≈ 0.08` ゲートで dormant な人物を1名だけ浮上させる(Proust 効果の人物版)。explicit filter (`emotion_filter` / `category_filter` / `date_from` / `date_to`) 指定時は involuntary のみ抑制し、resonant は維持
- ego-mcp: `wake_up` / `introspect` / `attune` の応答に「いま頭の隅にある人」を1〜2名織り込むスキャフォールドを追加
- ego-mcp: `attune` に optional `person` 引数を追加(`consider_them` と同じパターン、デフォルトは `companion_name`)。「誰を思いながら耳を澄ますか」という文脈付けで、CRM 的な対象指定ではない
- ego-mcp: `consolidate` に person backfill ステップを追加 — relationship store の `shared_episode_ids` に紐づいているのに `involved_person_ids` が空のメモリへ person id を埋め直す。一括移行ではなく consolidate サイクルで段階的に育てる
- ego-mcp: テレメトリ拡張 — `recall` に `surfaced_person_ids` / `resonant_person_ids` / `involuntary_person_ids` を、`remember` に `involved_person_ids` を、`consider_them` に対象 `person_id` を、`wake_up` / `introspect` / `attune` に `active_person_ids` を出力
- dashboard: Relationships タブを新設(`/api/v1/relationships/overview`, `/api/v1/relationships/surface-timeline`, `/api/v1/relationships/{person_id}/detail`)— 人物概観テーブル、surface timeline、人物別ドリルダウン (trust 推移 / shared episodes 推移 / surface 頻度) を表示

### Changed
- バージョンアップ: ego-mcp `1.0.1` → `1.1.0`, dashboard `0.2.4` → `0.3.0`, dashboard/frontend `0.2.4` → `0.3.0`

## [0.6.2] - 2026-04-03

### Changed
- ego-mcp: 動的欲求を prose label ではなく `grasp_something` のような stable ID で内部管理するよう変更し、`satisfy_desire` は active な emergent desire ID を直接受け付けるよう改善
- ego-mcp: `satisfy_desire` が legacy な emergent desire sentence も後方互換として受け付けるようにし、既存の推論フローからでも充足できるよう改善
- ego-mcp: migration `0006_emergent_desire_ids` で既存 `desire_state.json` の emergent desire key を canonical ID へ正規化し、書き換え前バックアップを保持するようにした
- dashboard: Current / desire key API が返す動的欲求 key の扱いを stable ID ベースとして文書化
- バージョンアップ: ego-mcp `0.6.1` → `0.6.2`

## [0.5.0] - 2026-03-28

### Added
- ego-mcp: Notion に `related_notion_ids`, `reinforcement_count`, `person_id` を追加し、migration `0004_notion_fields` で既存データを拡張
- ego-mcp: `curate_notions` ツールを追加し、notion の list / merge / relabel / delete を MCP から実行可能にした
- dashboard: `/api/v1/notions` が reinforcement / conviction / person / related notion 情報を返し、`/api/v1/memory/network` が `notion_related` edge を返すよう拡張

### Changed
- ego-mcp: `consolidate` が ephemeral cluster を除外し、notion 生成後に decay / prune / duplicate merge / auto-link を行う self-maintenance フローへ移行
- ego-mcp: `wake_up`, `introspect`, `consider_them`, `am_i_being_genuine`, `recall` が notion baseline / framework / person impressions / convictions / related notions を surfacing
- dashboard: History タブの Notion / Memory Network パネルが conviction, person, reinforcement, related notion 情報を表示
- バージョンアップ: ego-mcp 0.4.3→0.5.0, dashboard 0.2.3→0.2.4, dashboard/frontend 0.2.3→0.2.4

### Design
- `design/wip/v0.5.0-notion-enhancement-design.md` — Notion System Enhancement 設計書

## [0.4.3] - 2026-03-28

### Fixed
- ego-mcp: `remember` が docs にある感情ラベル（`calm`, `grateful`, `warm` など）を保存時に `neutral` へ潰してしまう問題を修正
- ego-mcp: `consider_them` が単なる参照操作にもかかわらず `total_interactions` や mood trajectory を増やしてしまう副作用を除去し、推論した話題は出力にのみ反映するよう修正
- ego-mcp: `link_memories` が同一 memory pair に対して 1 種類の link しか持てず、`SIMILAR` と `CAUSED_BY` / `LEADS_TO` を共存できない問題を修正
- ego-mcp: `recall` の `--- notions ---` が tag 一致だけに依存して source memory 由来の Notion を取りこぼす問題を修正
- dashboard: Notion confidence 履歴が複数 notion 同時更新時に混線する問題を修正し、notion 単位の confidence map を保存・集計するよう変更
- dashboard: History タブのプリセット範囲がポーリング中に前進しない問題と、current snapshot に出ていない動的 desire 系列が履歴から消える問題を修正
- dashboard: Notion パネルが notion history API を使わず静的一覧止まりだった問題を修正し、選択 notion の confidence trend を表示
- dashboard: `dashboard/docker-compose.yml` で backend に `DASHBOARD_EGO_MCP_DATA_DIR` を渡すだけで実データを mount していなかった問題を修正

### Changed
- dashboard API に `GET /api/v1/desires/keys` を追加し、History タブの動的 desire key 検出を backend 集約へ変更
- Dashboard Memory Network API が memory node の `label` を返すよう改善
- リリース用 version を更新: ego-mcp `0.4.2` → `0.4.3`, dashboard `0.2.2` → `0.2.3`, dashboard/frontend `0.2.2` → `0.2.3`

## [0.4.2] - 2026-03-28

### Fixed
- Dashboard Memory Network API が `ego_mcp` 内部モジュールの import に依存していたため、docker compose の backend コンテナから常に空表示になる不具合を修正。Chroma metadata を dashboard 側だけで直接読み取り、コンテナ運用でも記憶ノードとリンクを描画できるように変更
- Dashboard Memory Network / Notions パネルがモバイル幅で縮まず、History タブ全体の横幅を押し広げてしまう不具合を修正（`min-w-0` / `overflow-hidden` を適用）
- Memory Network の memory 読み込みに失敗した際でも Notion ノードまで消えてしまうフォールバック不備を修正

### Changed
- `dashboard/docker-compose.yml` に `DASHBOARD_EGO_MCP_DATA_DIR` の backend 受け渡しを追加し、`.env.example` に設定欄を追加
- バージョンアップ: ego-mcp 0.4.1→0.4.2, dashboard 0.2.1→0.2.2, dashboard/frontend 0.2.1→0.2.2

## [0.4.0] - 2026-03-22

### Added

#### A. 記憶基盤の強化
- **Spreading Activation** — recall 時に上位結果の linked_ids を 1-hop 辿り、リンク先記憶も候補に追加。confidence による重み付け。フィルタ付き recall では無効化
- **Confidence の実効化** — 高 confidence リンクで繋がった記憶群の半減期を最大 1.5x 延長。低 confidence (< 0.1) リンクは consolidate 時に自動消滅
- **Consolidate リンク戦略拡張** — 感情的類似（同 emotion, intensity 差 < 0.2）、テーマ的類似（共通タグ 2+）、クロスカテゴリ（異カテゴリ, semantic distance < 0.25）のリンク自動作成
- **因果リンクの促進** — remember スキャフォールドに `link_memories` による因果リンク（CAUSED_BY/LEADS_TO）の促しを追加
- **Memory access_count / last_accessed** — recall で返された記憶の access_count をインクリメント。繰り返し想起された記憶は半減期が動的に延長（最大 +60 日）
- **Fuzzy Recall（うろ覚え）** — decay スコアに応じた 3 段階の鮮明度劣化。解釈的ラベルは付与せず decay 数値のみ表示
- **エピソード記憶の再浮上** — remember 時に dormant エピソード記憶との semantic distance を計算し、類似度が高ければ結果に含める（access_count もインクリメント）
- **プルースト効果（不随意想起）** — recall 時に確率的（25%）に dormant 記憶を 1 件混入。Hopfield ネットワークで候補選定。特別なラベルなし、decay スコアのみ。importance/emotion バイアスなし
- **Notion（観念）データ型** — エピソード記憶から抽出された抽象知識。consolidate 時のリンククラスタ検出（Bron-Kerbosch）→ 構造データから機械的に生成（LLM 要約なし）
- **Notion 強化・弱化** — remember 時にタグマッチする Notion の confidence を valence 方向に応じて増減。閾値 (0.2) 以下で dormant 化
- **recall 時の Notion 参照** — 関連 Notion を `--- notions ---` セクションで表示（label + emotion_tone + confidence のみ）
- `remember` ツールに `tags` パラメータを追加

#### B. 欲求システムの深化
- **欲求ブレンド（不透明化）** — feel_desires / wake_up / introspect の出力を数値ラベル形式から体感記述に変更。Dashboard テレメトリには引き続き数値を送信
- **動的欲求生成** — Notion (confidence ≥ 0.7) から emergent desire を自動生成。emotion_tone + valence → 抽象的な欲求方向テンプレート。72 時間未充足で自然消滅、充足後 7 日で除去
- **不合理な衝動（プルースト連動）** — dormant 記憶浮上時に emotion_tone に応じた一時的欲求ブースト（最大 +0.2, 1 回消費, 72h クールダウン）
- **事後的欲求接続** — remember スキャフォールドに satisfy_desire への事後的気づきの促しを追加

#### C. Dashboard 拡張
- **Memory Network パネル** — `GET /api/v1/memory/network` + SVG グラフ可視化（ノード: 記憶 + Notion、エッジ: リンク + notion_source）
- **Notion パネル** — `GET /api/v1/notions`, `GET /api/v1/notions/{id}/history` + テーブル表示（confidence バー, emotion badge）
- **Consolidation テレメトリ** — replay_events, new_links, link_types, pruned_links, notions_created をテレメトリに追加
- **忘却・再浮上テレメトリ** — fuzzy_recall_count, resurfaced_memory_id, proust_triggered/memory_id/memory_decay をテレメトリに追加
- **欲求拡張表示** — NOW タブ: 欲求レーダーに動的欲求（別色）+ 衝動ブーストのハイライト。HISTORY タブ: 動的欲求の推移 + 衝動ブーストマーカー
- **Proust マーカー** — 感情タイムラインにプルースト効果発生をマーカー + バッジで重畳表示
- Ingestor に Notion / impulse / emergent desire メトリクスのプロジェクション追加

### Changed
- `requires-python` を `">=3.14"` に更新
- CI の Python バージョンを 3.14 に更新
- バージョンアップ: ego-mcp 0.3.0→0.4.0

### Design
- `design/wip/v0.4.0-design.md` — v0.4.0 全体設計書

## [dashboard 0.2.1] - 2026-03-02

### Added
- Dashboard History タブに Emotion trend チャートを追加し、`neutral` を中央（0）に固定した感情名（`curious`, `happy`, `sad` など）軸で時系列変化を表示

### Changed
- Dashboard History タブのパネル順を調整し、`Intensity history` の直後に `Emotion trend` を配置（`Emotion distribution` と隣接）
- バージョンアップ: dashboard 0.2.0→0.2.1, dashboard/frontend 0.1.0→0.2.1

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
