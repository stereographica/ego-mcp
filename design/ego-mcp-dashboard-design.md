# ego-mcp 利用状況ダッシュボード設計ドキュメント（提案）

## 1. 目的と前提

### 1.1 目的
- ego-mcp の**現在状態をリアルタイムに可視化**し、運用中の状況変化を「眺めて把握できる」こと。
- 併せて、過去の利用傾向（ツール使用回数やパラメータ推移）を**時系列分析**できること。
- private データを意図せず表示しない安全設計を最優先にすること。

### 1.2 前提
- 同一リポジトリ内だが、`ego-mcp/` とは別ディレクトリに新規プロジェクトとして実装する。
- ダッシュボードは websocket によるライブ更新をサポートする。
- 現在ログは `/tmp` 配下出力だが、live tail 実装都合で出力先変更は許容する。

---

## 2. 要件整理（確定 / あいまい）

### 2.1 確定要件
1. ツールごとの使用回数を可視化する。
2. タイムレンジ指定でグラフ表示できる。
3. `emotion` / `intensity` 等の現在値と推移を可視化する。
4. `int` / `float` はグラフ化、`string` は別表現を検討する。
5. アプリケーションログの live tail を提供する。
6. 初期表示は「現在時点」にフォーカスし、放置観察で変化が追えること。
7. UI は shadcn でシンプルかつ見やすく。
8. private データを表示しない。
9. ego-mcp からのデータ取得方式（telemetry 含む）を設計する。
<<<<<<< ours
=======
10. `docker-compose` で開発環境/検証環境を起動できること。
11. 実装だけでなく運用者向けドキュメント（起動、設定、トラブルシュート）を整備すること。
>>>>>>> theirs

### 2.2 あいまい要件と提案
- 「ライブリロード頻度」: 1秒以下は不要。**1–2秒バッチ更新**（サーバ側集約）を推奨。
- 「string パラメータの推移」: 折れ線ではなく、**カテゴリ遷移タイムライン**（色付きバッジ列）を推奨。
- 「live tail の保持期間」: メモリ常駐は危険。**UI は直近 N 行のみ、履歴は別 API**が妥当。
- 「テレメトリ方式」: まずは**既存 JSONL ログ活用 + 追記イベント**が低リスク。

---

## 3. 全体アーキテクチャ提案

## 3.1 コンポーネント
- `dashboard/`（新規）
  - `frontend`（Next.js + shadcn/ui）
  - `backend`（FastAPI など）
  - `ingestor`（ログ/イベント取り込み、集計、WS配信）
  - `storage`（Timeseries + 軽量RDB）

## 3.2 データフロー（推奨）
1. ego-mcp が JSONL ログを出力（既存）。
2. ingestor がファイル tail し、イベントを正規化。
3. 正規化イベントを時系列ストレージへ保存。
4. backend が
   - REST: 履歴取得（タイムレンジ指定）
   - WebSocket: 現在値 push
   を提供。
5. frontend は初期表示で「Now ダッシュボード」を開き、WS 購読で自動更新。

## 3.3 なぜこの構成か
- ego-mcp 本体への改修を最小化しやすい。
- dashboard 側で安全フィルタを強制できる。
- 将来、ログ以外（OTel/メッセージキュー）に移行しやすい。

---

## 4. データ取得戦略（telemetry 方針）

## 4.1 結論
**Phase 1 は「構造化ログ由来 telemetry」方式を推奨。**
- 理由: 既に tool invocation / completion がログ出力されており、導入コストが低い。
- 追加で必要な項目のみ ego-mcp 側ログに `extra` フィールドとして追記する。

## 4.2 Phase 2（拡張）
- OpenTelemetry（OTLP）へ発展させ、
  - traces: tool 実行単位
  - metrics: 使用回数・レイテンシ
  - logs: 既存JSONL
  を統合可能にする。

## 4.3 収集イベント最小スキーマ（案）
```json
{
  "ts": "2026-01-01T12:00:00Z",
  "event_type": "tool_call_completed",
  "tool_name": "feel_desires",
  "duration_ms": 42,
  "ok": true,
  "emotion_primary": "curious",
  "emotion_intensity": 0.72,
  "params": {
    "valence": 0.2,
    "arousal": 0.6,
    "time_phase": "night"
  },
  "private": false
}
```

### private 保護ルール
- `private=true` データは本文保存禁止（件数カウントのみ許可）。
- テキスト本文や recall 結果は保存しない。
- ログtail画面では `REDACTED` マスクを再適用（多層防御）。

---

## 5. 保存設計（履歴 + リアルタイム）

## 5.1 推奨構成
- **Timeseries DB**: TimescaleDB or ClickHouse（推奨は運用容易な TimescaleDB）
- **キャッシュ**: Redis（WS配信バッファ、最新スナップショット）
- **ローテーション**: raw log は短期、集計テーブルは中長期

## 5.2 テーブル（概念）
- `tool_events(ts, tool_name, ok, duration_ms, private_flag, ... )`
- `metric_points(ts, key, value_float, value_int, value_str, source)`
- `log_events(ts, level, logger, message, masked_json)`
- `current_snapshot(updated_at, payload_json)`

---

## 6. API / WebSocket 設計

## 6.1 REST API（履歴取得）
- `GET /api/v1/usage/tools?from=&to=&bucket=1m`
  - ツール別使用回数（時系列）
- `GET /api/v1/metrics/{key}?from=&to=&bucket=1m`
  - 数値/文字列メトリクス時系列
- `GET /api/v1/logs?from=&to=&level=`
  - マスク済みログ履歴
- `GET /api/v1/current`
  - 初期表示用スナップショット

## 6.2 WebSocket（現在フォーカス）
- `WS /ws/current`
  - 1–2秒周期で差分 push
  - イベント例:
```json
{ "type": "current_snapshot", "at": "...", "data": { ... } }
{ "type": "tool_event", "data": { "tool": "remember", "ok": true } }
{ "type": "metric_update", "data": { "key": "intensity", "value": 0.61 } }
{ "type": "log_line", "data": { "level": "INFO", "message": "..." } }
```

## 6.3 接続安定化
- ping/pong heartbeat（30秒）
- 再接続時は `last_event_id` 指定でギャップ補完
- UI 側は exponential backoff

---

## 7. UI/UX 設計（shadcn）

## 7.1 ナビゲーション
- タブA: **Now（初期表示）**
- タブB: **History**
- タブC: **Logs**

## 7.2 Now タブ（最重要）
- 上段: 現在サマリーカード
  - tool calls/min
  - error rate
  - latest emotion / intensity
- 中段: リアルタイムチャート
  - intensity, valence, arousal（折れ線）
- 下段: イベントフィード
  - 最新ツール実行・警告ログ（private はマスク表示）

## 7.3 History タブ
- TimeRange picker（15m / 1h / 6h / 24h / 7d / custom）
- ツール使用回数（stacked bar / area）
- 数値パラメータ推移（multi-line）
- string パラメータ
  - 提案1: 状態遷移タイムライン
  - 提案2: 出現頻度ヒートマップ

## 7.4 Logs タブ
- live tail（下に追記）
- level / logger フィルタ
- 自動スクロール ON/OFF
- private 検知時は行全体を `REDACTED` 置換

## 7.5 shadcn コンポーネント候補
- `Card`, `Tabs`, `Badge`, `Select`, `Popover`, `Command`, `Table`, `Tooltip`, `Skeleton`, `Alert`
- チャートは `recharts` か `visx` を薄くラップして統一テーマ適用

---

## 8. private データ保護設計

1. **収集段階**: private フィールドを破棄 or 不可逆マスク。
2. **保存段階**: PII/本文を格納しないスキーマ設計。
3. **配信段階**: API レスポンスに safety filter を共通適用。
4. **表示段階**: UI で再検査し、危険文字列は伏せ字化。
5. **監査段階**: 「何をマスクしたか」を監査ログへ記録。

推奨: 「表示可能フィールド allow-list」方式で実装。

---

## 9. ログ出力先方針（/tmp 問題）

## 9.1 課題
- `/tmp` は再起動や環境差分で消える可能性があり、監視対象として不安定。

## 9.2 提案
- ego-mcp 側に `EGO_MCP_LOG_PATH` 環境変数を追加し、既定値 `/tmp/...` を維持。
- 本番/常設環境では `./var/log/ego-mcp/*.log` 等へ切替可能にする。
- ingestor はパス設定を共有し、ローテーション追従（inode 監視）を実装。

---

## 10. 開発フェーズ提案

### Phase 0: 設計固定（本ドキュメント）
- KPI と private ポリシー定義
- 収集項目の最終確定

### Phase 1: MVP（2〜3週間）
- JSONL tail ingestor
- REST + WS 基本API
- Now タブ + Logs タブ
- ツール使用回数 / intensity 可視化

### Phase 2: 履歴分析強化
- History タブ拡充
- string パラメータ可視化（タイムライン + ヒートマップ）
- 異常検知（急増/急落アラート）

### Phase 3: telemetry 高度化
- OpenTelemetry 対応
- 分散トレース/メトリクス統合

---

## 11. 技術スタック提案（別ディレクトリ前提）

- Frontend: Next.js (App Router) + TypeScript + shadcn/ui + Tailwind
- Backend: FastAPI + Pydantic + Uvicorn
- Realtime: WebSocket（FastAPI or dedicated gateway）
- Storage: PostgreSQL + TimescaleDB（まずは単一DBで運用簡素化）
- Ingest: Python asyncio tailer（watchfiles / watchdog）
- Observability: Prometheus exporter（ダッシュボード自身の健全性監視）

<<<<<<< ours
=======
### 11.1 コンテナ実行要件（追加）
- `dashboard/` 直下に `docker-compose.yml` を配置し、少なくとも以下サービスを定義する。
  - `frontend`
  - `backend`
  - `ingestor`
  - `db`（PostgreSQL/TimescaleDB）
  - `redis`（採用する場合）
- `docker compose up -d` で起動し、初期画面表示まで確認できることを MVP の受け入れ条件に含める。
- 環境変数は `.env.example` を提供し、必須値を明示する。

### 11.2 ドキュメント整備要件（追加）
- 最低限、以下ドキュメントを `dashboard/docs/` に用意する。
  1. `getting-started.md`（ローカル起動手順、docker-compose 手順）
  2. `configuration.md`（環境変数、ログパス、private マスキング設定）
  3. `operations.md`（監視、バックアップ、ログローテーション、障害対応）
  4. `api.md`（REST/WS 契約、認可、レート制限）
- ドキュメントは「開発者向け」と「運用者向け」で章を分け、更新責任者を明記する。
- 主要機能（Now/History/Logs）は画面キャプチャまたは簡易図を添付する。

>>>>>>> theirs
---

## 12. リスクと対策

- **高頻度イベントでWS輻輳**
  - 対策: サーバ側で 1秒窓に集約して配信。
- **private データ混入**
  - 対策: 収集時・配信時の二重マスク + allow-list。
- **ログフォーマット変化で取り込み破綻**
  - 対策: スキーマバージョン付与、unknown フィールド許容。
- **/tmp ログ消失**
  - 対策: 出力先を可変にし、永続領域へ移行可能化。

---

## 13. 受け入れ基準（Definition of Done）

1. Now タブを開いたまま、ツール実行に応じて 2秒以内に表示が更新される。
2. ツール別使用回数を任意タイムレンジで可視化できる。
3. `intensity` 等の数値パラメータ推移を時系列表示できる。
4. string パラメータを少なくとも1種類の非グラフ表現で確認できる。
5. Logs タブで live tail 可能、private 行は必ずマスクされる。
6. 初期表示は Now タブで、最新状態を主役にしたレイアウトである。
<<<<<<< ours
=======
7. `docker compose up -d` で依存サービスを含めて起動し、疎通確認が完了している。
8. 起動・設定・運用・API のドキュメントが整備され、第三者が再現可能である。
>>>>>>> theirs

---

## 14. 実装開始時の具体アクション（推奨）

1. `dashboard/` ディレクトリ新設（frontend/backend/ingestor モノレポ構成）。
2. JSONL 1ファイルから tool usage と intensity を抽出する PoC ingestor を作成。
3. `/api/v1/current` と `/ws/current` の最小実装。
4. shadcn で Now タブ（3カード + 1折れ線 + イベントリスト）作成。
5. private フィルタのユニットテストを先行作成。

以上。
