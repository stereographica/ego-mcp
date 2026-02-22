# 実装監査レポート（Phase 3b: 記憶・感情・忘却拡張）

監査対象:
- `tasks/600-emotion-enum-expansion.md`
- `tasks/601-remember-link-visibility.md`
- `tasks/602-recall-filter-enhancement.md`
- `tasks/603-question-lifecycle.md`
- `tasks/604-emotion-trend.md`
- `tasks/605-forgetting-desire-integration.md`

監査日: 2026-02-22

## 実行結果

### テスト/型チェック
- `cd ego-mcp && uv run pytest tests/ -v`
  - 結果: **209 passed**, 失敗なし
- `cd ego-mcp && uv run mypy src/ego_mcp/`
  - 結果: **Success: no issues found in 20 source files**

### タスク達成判定（要件準拠）
- **T-600（Emotion enum 拡張）**: 達成
- **T-601（remember リンク可視化）**: 達成
- **T-602（recall フィルタ + search_memories 廃止）**: 達成
- **T-603（未解決の問い: 解決・重要度・忘却）**: 達成
- **T-604（emotion_trend 新設）**: 達成
- **T-605（忘却と欲求の連動）**: 達成

## 総評

全タスクの要件を満たしており、テスト・型チェックともに clean。設計意図との乖離も見られない。**品質は良好**。

以下は、設計意図との軽微な差異やコード品質上の改善提案であり、機能的な不具合は確認されていない。

---

## 発見事項（優先度順）

### 1. 【Medium】private 属性へのアクセスが 3 箇所にある

- **該当箇所**:
  - `server.py:700` — `memory._config.data_dir`（`_self_model_store_for_memory`）
  - `server.py:753,755` — `memory._embedding_fn`（`_find_related_forgotten_questions`）
  - `server.py:1332` — `memory._ensure_connected().count()`（`_handle_recall`）
- **内容**:
  - `MemoryStore` の `_config`, `_embedding_fn`, `_ensure_connected` はいずれも `_` プレフィックスの非公開メンバーであり、外部からのアクセスはカプセル化違反にあたる。
  - `_self_model_store_for_memory` は新設関数であり、この機会に公開インターフェースを用意すべき。
- **推奨対応**:
  - `MemoryStore` に以下を追加:
    - `@property data_dir` → `self._config.data_dir` を返す
    - `def embed(texts: list[str]) -> list[list[float]]` → `self._embedding_fn(texts)` を返す
    - `def collection_count() -> int` → `self._ensure_connected().count()` を返す
  - 呼び出し側を公開 API 経由に切り替える

### 2. 【Medium】`_fading_important_questions` が 1 リクエスト内で複数回呼ばれる

- **該当箇所**:
  - `server.py:800` — `_derive_desire_modulation` 内の early return パス
  - `server.py:855` — `_derive_desire_modulation` 内のメインパス
  - `server.py:961` — `_handle_feel_desires` 内
- **内容**:
  - `_handle_feel_desires` → `_derive_desire_modulation` の呼び出しで、`_fading_important_questions` は最大 2 回（`_derive_desire_modulation` 内で 1 回 + `_handle_feel_desires` で 1 回）呼ばれる。
  - `_fading_important_questions` は毎回 `SelfModelStore` を新規生成し、ファイルの読み込み + question_log の走査 + salience 計算を行う。
  - 同様に `_handle_introspect` は `_derive_desire_modulation` を呼ぶため、ここでも `_fading_important_questions` と `get_visible_questions` でファイルが 2 回読まれる。
- **推奨対応**:
  - `_derive_desire_modulation` の返り値に `fading_important` のリストを含めて呼び出し元に渡すか、`_handle_feel_desires` / `_handle_introspect` の冒頭で 1 回だけ取得してキャッシュする。

### 3. 【Medium】`_count_emotions_weighted` が `_` プレフィックス付きで memory.py から外部 import されている

- **該当箇所**:
  - `memory.py:103` — `def _count_emotions_weighted(...)`
  - `server.py:22` — `from ego_mcp.memory import ..., _count_emotions_weighted, ...`
- **内容**:
  - `_` プレフィックスは慣例上モジュール非公開を意味するが、`server.py` から直接 import している。mypy は通るが、API 設計として不整合。
- **推奨対応**:
  - `_count_emotions_weighted` → `count_emotions_weighted` にリネームする（公開 API として扱う）。

### 4. 【Low】`import math` の位置が PEP 8 / isort の慣例に反している

- **該当箇所**: `server.py:5-6`
  ```python
  from collections import Counter
  import math
  ```
- **内容**:
  - PEP 8 および isort のデフォルトルールでは `import xxx` が `from xxx import yyy` より前に来る。stdlib の `import math` が `from collections import Counter` の後に置かれている。
- **推奨対応**:
  - `import math` を `from collections import Counter` の前に移動する。

### 5. 【Low】`_format_recall_entry` / emotion_trend のヘルパー群が `list[Any]` 型を使っている

- **該当箇所**:
  - `server.py:469` — `_format_recall_entry(index, result: Any, ...)`
  - `server.py:535-536` — `_memories_within_days(memories: list[Any], ...)`
  - `server.py:552` — `_secondary_weighted_counts(memories: list[Any])`
  - `server.py:576,606,651` — `_format_recent/week/month_emotion_layer(memories: list[Any], ...)`
- **内容**:
  - `mypy --strict` は pass しているが、`list[Any]` は事実上の型チェック放棄。`Memory` 型や `MemorySearchResult` 型を直接指定すべき。
  - `_format_recall_entry` の `result: Any` も `MemorySearchResult` が適切。
- **推奨対応**:
  - `list[Any]` → `list[Memory]`、`result: Any` → `result: MemorySearchResult` に変更する。
  - 必要に応じて `from ego_mcp.types import Memory, MemorySearchResult` を追加。

### 6. 【Low】`_sanitize_tool_output_for_logging` の recall 用正規表現が新フォーマットに対応しているが、テストが不足

- **該当箇所**: `server.py:299-316`
- **内容**:
  - recall のレスポンスフォーマットが 2 行形式（`1. [2d ago] content\n   emotion: ... | private`）に変わったため、sanitize ロジックが multi-line 対応に書き換えられている。
  - しかし、`TestToolLoggingPrivacy` にこの新しい 2 行フォーマットに対する直接的なテストケースがない。既存テストは全体的な「private が redact される」を検証しているが、行をまたぐパターンが正しく動作するかの単体テストが望ましい。
- **推奨対応**:
  - `_sanitize_tool_output_for_logging` に対して、新しい 2 行フォーマットの recall 出力を入力とするユニットテストを追加する。

### 7. 【Medium】`_format_month_emotion_layer` の fading タグ判定条件が設計と異なる

- **該当箇所**: `server.py:693-694`（`_format_month_emotion_layer` 内）
- **設計書の条件**（§3.4）:
  - 該当期間の記憶の平均 `time_decay` が 0.5 未満 **かつ** 同じ感情が直近 1 週間に出現していない（AND 条件）
- **実装の条件**:
  ```python
  if fading_emotion and (avg_decay < 0.5 or candidate_decay < 0.6):
  ```
  - `fading_emotion`（週に未出現の感情）の抽出は正しいが、decay 条件が OR になっている
  - これにより **当該感情の decay が高くても月全体の decay が低ければ fading 判定される**
  - 例: ある感情が最近まで頻繁に出現しており candidate_decay が 0.8 でも、他の記憶全体の avg_decay が 0.4 であれば fading と判定されてしまう
- **推奨対応**:
  - 設計通りの AND 条件に修正する。`avg_decay` は月全体ではなく当該感情の記憶の平均に限定するのが設計意図に沿う:
    ```python
    if fading_emotion and candidate_decay < 0.5:
    ```
  - または設計書の条件を厳密に再現するなら:
    ```python
    if fading_emotion and avg_decay < 0.5 and candidate_decay < 0.5:
    ```

### 8. 【Low】`_handle_introspect` で `_derive_desire_modulation` を再呼び出しして coherence_level を算出している

- **該当箇所**: `server.py:987-995`
- **内容**:
  - `_handle_introspect` が `_derive_desire_modulation` + `desire.compute_levels_with_modulation` を呼んで `coherence_level` を算出している。これは Resurfacing セクションの表示条件（`coherence_level >= 0.6`）のためだけに使われている。
  - `introspect` は元々欲求計算を行わないツールだったので、欲求計算の副作用（`list_recent(n=30)` の再取得 + question log の再読み込み）が追加されている。
- **影響**:
  - パフォーマンス影響は軽微だが、#2 と合わせて考えると不要な I/O の重複がある。
- **推奨対応**:
  - #2 と合わせて、`_handle_introspect` 冒頭で fading questions を 1 回取得し、その有無だけで Resurfacing の表示判断を行う簡易版にリファクタリングする余地がある。ただし設計上「coherence_level >= 0.6 の時だけ表示」という条件を維持するかは判断が必要。

---

## 設計意図との照合

| 設計項目 | 合致 | 備考 |
|---|---|---|
| Emotion 4 値追加 | ✅ | 値・順序ともに設計通り |
| EMOTION_BOOST_MAP 拡張 | ✅ | 値が設計通り |
| `_derive_desire_modulation` の frustrated 対応 | ✅ | prediction_error に含めている |
| `_derive_desire_modulation` の anxious 対応 | ✅ | cognitive_coherence + social_thirst にブースト |
| remember Top 3 + scaffold | ✅ | similarity 表示・truncate・scaffold 問いかけ全て実装 |
| `save_with_auto_link` 返り値拡張 | ✅ | 3 要素タプルに変更済み |
| `_relative_time` 関数 | ✅ | 各バケットのテストあり |
| recall に date_from/date_to 追加 | ✅ | スキーマ・ハンドラともに実装 |
| recall n_results 上限キャップ | ✅ | `min(int(raw), 10)` で実装 |
| recall 結果表示改善 | ✅ | 相対時間・undercurrent・total count・intensity 数値条件付き表示 |
| search_memories 廃止 | ✅ | BACKEND_TOOLS・dispatch・ハンドラ全て削除、テスト更新 |
| 動的 scaffold | ✅ | `_recall_scaffold` でフィルタ使用状況に応じた案内 |
| question_log に importance/created_at | ✅ | add_question 拡張・フォールバック処理あり |
| resolve_question via update_self | ✅ | `field="resolve_question"` 分岐追加 |
| question_importance via update_self | ✅ | `field="question_importance"` 分岐追加 |
| salience 計算 | ✅ | 設計通りの計算式（半減期 = importance * 14） |
| get_visible_questions | ✅ | Active/Fading/Dormant の 3 分類 |
| introspect の問い表示改修 | ✅ | question ID・importance 表示・resolve 案内 |
| Resurfacing セクション表示条件 | ✅ | coherence_level >= 0.6 or 関連記憶トリガー |
| emotion_trend（バックエンドツール） | ✅ | 3 層時間窓・graceful degradation 実装 |
| 加重感情カウント | ✅ | primary=1.0, secondary=0.4 |
| 月次印象語 | ✅ | 6 パターンのマッピング |
| ピーク・エンドの法則 | ✅ | peak + end を月次に表示 |
| fading タグ | ⚠️ | 週内不出現条件は正しいが、decay の判定が AND→OR に緩和されている（#7） |
| graceful degradation | ✅ | 0/1-4/5-14/15-29/30+ の段階 |
| 忘却→再浮上（経路 1: remember） | ✅ | embedding 類似度で検出・レスポンスに表示 |
| 忘却→欲求（経路 2: cognitive_coherence） | ✅ | _derive_desire_modulation にブースト追加 |
| feel_desires の「引っかかり」scaffold | ✅ | coherence >= 0.6 + fading 存在時に追加 |
| SCAFFOLD_EMOTION_TREND 新設 | ✅ | |
| SCAFFOLD_INTROSPECT に emotion_trend 誘導追加 | ✅ | |
