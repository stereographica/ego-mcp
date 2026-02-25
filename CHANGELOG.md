# Changelog

このプロジェクトの主要な変更を記録する。

---

## predictability 欲求の充足改善 (2026-02-25)

### 変更

- **暗黙充足マップ拡張**: `wake_up` → `predictability` 0.05、`introspect` / `consider_them` に `predictability` 0.1 を追加
- **wake_up ルーティング改善**: `satisfy_implicit("wake_up")` 呼び出しを追加し、セッション開始時に微量の予測欲求を充足
- **スキャフォールド改善**: `feel_desires`, `introspect`, `consider_them` の 3 スキャフォールドに予測検証・確認の促し文言を追加し、Claude が自発的に `satisfy_desire("predictability")` を呼べるように誘導

---

## Phase 3b — 記憶・感情・忘却拡張 (2026-02-22)

### 新機能

- **Emotion enum 拡張**: `melancholy`, `anxious`, `contentment`, `frustrated` の 4 感情を追加し、valence-arousal 空間上のネガティブ象限の表現力を向上
- **emotion_trend バックエンドツール**: 3 層時間窓（vivid / moderate / impressionistic）による感情パターンの俯瞰分析を新設
  - Undercurrent（底流）分析: secondary 感情の加重カウントで表面に現れない感情の流れを検出
  - 月次印象語: valence-arousal 平均から人間的な印象語を生成
  - ピーク・エンドの法則: 月次サマリに intensity 最大の記憶と最新の記憶を明示
  - fading タグ: 時間経過で印象が薄れる感情クラスタを可視化
  - Graceful Degradation: 記憶数に応じて段階的に機能をリッチにする
- **remember リンク記憶の可視化**: 保存時にセマンティック類似度の高い既存記憶を最大 3 件表示し、連想の展開を促進
- **未解決の問いのライフサイクル**:
  - importance（1-5）と created_at を question_log に追加
  - salience に基づく自然な忘却（Active → Fading → Dormant）
  - `update_self(field="resolve_question")` で問いを解決済みにする機能
  - `update_self(field="question_importance")` で重要度を変更する機能
  - introspect の Resurfacing セクションで「ふと思い出す」体験を再現
- **忘却と欲求の連動**:
  - 経路 1: remember 時に dormant/fading な問いとの embedding 類似度を比較し、関連があれば再浮上
  - 経路 2: fading 状態の高重要度の問いが cognitive_coherence 欲求にブースト（「何か引っかかる」感覚）
  - feel_desires に「nagging feeling」スキャフォールドを追加

### 変更

- **recall フィルタ強化**: `date_from` / `date_to` パラメータを追加し、日付範囲での絞り込みが可能に
- **recall 結果表示の刷新**: 相対時間表記、undercurrent 表示、intensity の条件付き数値表示、total count 表示
- **recall の動的スキャフォールド**: 使用されたフィルタに応じてスキャフォールドのフィルタ案内を動的に切り替え
- **recall の n_results 上限キャップ**: 最大 10 件に制限（デフォルト 3 件は維持）
- **introspect の問い表示改修**: question ID と importance を表示し、resolve の案内を追加
- **EMOTION_BOOST_MAP 拡張**: 新感情 4 種にブースト値を設定（frustrated: 0.28, anxious: 0.22, melancholy: 0.18, contentment: 0.08）
- **`_derive_desire_modulation` の拡張**: frustrated → prediction_error、anxious → cognitive_coherence + social_thirst にブースト
- **`save_with_auto_link` の返り値拡張**: リンク先の `MemorySearchResult` リストも返すように変更

### 削除

- **`search_memories` バックエンドツールの廃止**: 全機能を `recall` に統合。ツール総数は 15 のまま維持（emotion_trend が新設されたため ±0）

### 品質改善

- `MemoryStore` にカプセル化された公開 API を追加（`data_dir` property, `embed()`, `collection_count()`）
- `_count_emotions_weighted` を公開関数にリネーム（`count_emotions_weighted`）
- 型注釈の厳密化（`list[Any]` → `list[Memory]`, `result: Any` → `result: MemorySearchResult`）
- `_sanitize_tool_output_for_logging` の 2 行フォーマット対応テストを追加
- `_derive_desire_modulation` に引数キャッシュ導入（`fading_important_questions`, `recent_memories`）で I/O 重複を削減
- isort 導入による import 順序の統一

---

## Private Memory (2026-02-21)

### 新機能

- **private フラグ**: `remember(private=true)` で外部に出さない記憶を保存可能に
- **workspace sync 抑止**: private 記憶は `memory/*.md`, `MEMORY.md`, `inner-monologue-latest.md` に同期されない
- **ログ redaction**: private 記憶の本文はログに `[REDACTED_PRIVATE_MEMORY]` として記録
- **recall での private 表示**: 検索結果に `private` フラグを明示し、LLM の判断材料とする
- **wake_up スキャフォールド**: private 記憶の存在をさりげなく想起させる案内を追加

---

## Dashboard (2026-02-21)

### 新機能

- **利用状況ダッシュボード**: ego-mcp のツール使用状況をリアルタイムに可視化
  - Now タブ: サマリーカード + リアルタイムチャート + イベントフィード
  - History タブ: タイムレンジ指定でツール使用回数・パラメータ推移を分析
  - Logs タブ: マスク済みログの live tail
- **JSONL ログベースの telemetry**: 既存ログから構造化イベントを取り込み
- **private データ保護**: 収集・保存・配信・表示の 4 層でマスキング

---

## 初期リリース

- ego-mcp MCP サーバーの基本実装
- 表面ツール 7 個 + バックエンドツール 8 個
- ChromaDB ベースの記憶システム（セマンティック検索 + Hopfield パターン補完）
- 欲求システム（非線形計算 + 感情/記憶変調）
- 関係性モデル
- 自己モデル
- 内部独白
- OpenClaw workspace sync
- JSONL ランタイムログ
