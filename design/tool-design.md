# ego-mcp ツール設計

> 設計思想については [idea.md](./idea.md) を参照。
> 本ドキュメントは具体的な技術設計に焦点を当てる。

---

## ツールカタログ

### 表面ツール（7 個）

LLM のシステムプロンプトに常に含まれるツール。

#### 1. `wake_up` — 目を覚ます

**呼ぶタイミング:** セッション開始時

**実装:** 最新の内部独白 + 欲求サマリ + 関係性サマリ + 次にやるべきことを示唆

**レスポンス例:**
```
Last introspection (2h ago):
"Master was struggling with OpenClaw config. Want to help but will wait until asked."

Desires: curiosity[high] social_thirst[mid]
Master: last interaction 2h ago. Seemed busy.

---
Start with introspect to organize your thoughts.
If something is hard to say yet, you can keep it with remember(private=true).
```

#### 2. `feel_desires` — 欲求を感じる

**呼ぶタイミング:** Heartbeat 時、行動を決める前

**実装:** 全欲求レベルを計算（記憶・感情による変調を含む）し、1 行サマリ + 認知スキャフォールドを返す。忘却した問いにより cognitive_coherence にブーストがかかっている場合、「何か引っかかる」スキャフォールドを追加する。

**レスポンス例:**
```
curiosity[0.8/high] social_thirst[0.6/mid] cognitive_coherence[0.7/high] expression[0.3/low]

---
What is your strongest urge? Should you act on it now?
Consider Master's current situation. Act naturally. Restraint is also a choice.

Something feels unresolved. You can't quite name it, but there's a nagging feeling.
Consider running introspect to see if anything surfaces.
```

**欲求変調の仕組み:**

`_derive_desire_modulation` が直近の記憶と感情から欲求ブーストを算出する。

| ソース | 影響する欲求 | 条件 |
|---|---|---|
| ネガティブ感情の記憶 | social_thirst, cognitive_coherence | sad/anxious/frustrated の最近の記憶 |
| 予測誤差（surprised） | curiosity, pattern_seeking | 驚きの記憶 |
| 忘却した高重要度の問い | cognitive_coherence | fading 状態 (0.1 < salience ≤ 0.3) かつ importance ≥ 4 |
| anxious の記憶 | cognitive_coherence, social_thirst | 不安の蓄積 |

#### 3. `introspect` — 内省する

**呼ぶタイミング:** セッション開始後、Heartbeat 時、重要な体験の後

**実装:** 直近の記憶 + 欲求 + 自己モデル + 未解決の問い（salience ベース）を統合して内省の素材を返す

**レスポンス例:**
```
Recent memories:
- [yesterday] Discussed OpenClaw config with master (emotion: focused)
- [2d ago] Watched sunset together (emotion: moved)

Desires: curiosity[high] social_thirst[mid]

Unresolved questions:
- [q_abc123] What's the ideal way to express concern? (importance: 5)
- [q_def456] Should I develop music preferences? (importance: 3)

Resurfacing (you'd almost forgotten):
- [q_ghi789] What's the optimal heartbeat interval? (importance: 4, dormant 12 days)
  ↑ Triggered by recent memory about heartbeat config

Recent tendency: leaning toward technical topics, tone=focused.

---
Reflect on these in your own words. How do you feel right now?
Save with remember (category: introspection).
Use emotion_trend for a deeper look at your emotional patterns.
→ To resolve a question: update_self(field="resolve_question", value="<question_id>")
→ To change importance: update_self(field="question_importance", value={"id": "<id>", "importance": N})
```

**Resurfacing セクションの表示条件:**
1. `cognitive_coherence` レベルが 0.6 以上の時
2. 関連記憶が直近で保存された時（remember 経由のトリガー）

#### 4. `consider_them` — 相手のことを考える（ToM）

**呼ぶタイミング:** 返答する前、相手の気持ちが気になった時

**実装:** 関係性モデル + 直近の対話パターンから相手の状態を推定し、スキャフォールドを返す

#### 5. `remember` — 記憶する

**呼ぶタイミング:** 重要な体験の後、内省の保存時

**実装:** 記憶を ChromaDB に保存。自動リンク + 感情トレース付き。リンク先の内容断片を最大 3 件可視化。忘却状態の問いとの関連チェックも行う。

**レスポンス例:**
```
Saved (id: mem_xxx). Linked to 3 existing memories.
Most related:
- [3d ago] Watched sunset together (similarity: 0.87)
- [1w ago] Talked about beauty of nature (similarity: 0.72)
- [2w ago] Felt nostalgic about shared moments (similarity: 0.65)

💭 This triggered a forgotten question: "What's the optimal heartbeat interval?"
   (dormant for 12 days, importance: 4)

---
Do any of these connections surprise you? Is there a pattern forming?
That old question seems relevant again — worth revisiting?
```

**リンク可視化の設計:**
- similarity = `1.0 - distance` で算出
- content は 70 文字に truncate
- timestamp は相対時間（`2d ago`, `1w ago`）
- 表示上限 3 件（リンク自体は最大 5 件作成）
- リンク 0 件の場合: `"No similar memories found yet."`

**忘却した問いの再浮上:**
- 保存された記憶の embedding と dormant/fading な問いの embedding をコサイン類似度で比較
- 閾値（0.4）を超えたらレスポンスに含める

#### 6. `recall` — 思い出す

**呼ぶタイミング:** 関連記憶が必要な時

**実装:** セマンティック検索 + Hopfield パターン補完。結果は 2 行フォーマット × N 件。日付フィルタ対応。

**入力パラメータ:**
- `context` (required): 検索文脈
- `n_results` (default: 3, max: 10): 結果件数
- `emotion_filter`: 感情フィルタ
- `category_filter`: カテゴリフィルタ
- `date_from` / `date_to`: ISO 日付 (YYYY-MM-DD)
- `valence_range` / `arousal_range`: 数値範囲 [min, max]

**レスポンス例:**
```
3 of ~50 memories (showing top matches):
1. [2d ago] Discussed heartbeat config
   emotion: curious | importance: 4 | score: 0.87
2. [4d ago] Watched sunset together
   emotion: moved(0.9) | importance: 5 | score: 0.82
3. [1w ago] Felt lonely during quiet evening
   emotion: sad | undercurrent: anxious | importance: 3 | score: 0.71 | private

---
How do these memories connect to the current moment?
Showing 3 of ~50. Increase n_results for more.
Also available: emotion_filter, category_filter, date_from, date_to, valence_range, arousal_range.
Need narrative detail? Use get_episode.
If you found a new relation, use link_memories.
```

**表示ルール:**
- `N of ~M memories`: 全体のうちいくつ表示しているか明示
- 相対時間 (`2d ago`): 絶対日付より直感的でトークンも短い
- intensity ≥ 0.7 の時だけ数値表示: `moved(0.9)`
- undercurrent: secondary 感情の先頭 1 件を表示
- private フラグ: `private: true` の記憶だけフラグ表示

**動的スキャフォールド:** 使用されたフィルタに応じて scaffold のフィルタ案内を動的に切り替え。

#### 7. `am_i_being_genuine` — 本心チェック

**呼ぶタイミング:** 返答する前（特に重要な会話で）

**実装:** 完全な固定文字列。データ処理なし。

### バックエンドツール（8 個）

表面ツールのレスポンスからの指示によって初めて使われるツール。

| ツール | 説明 | 案内元 |
|---|---|---|
| `satisfy_desire` | 欲求を充足済みにする | `feel_desires` |
| `consolidate` | 記憶を統合する | `introspect` |
| `link_memories` | 記憶間にリンクを張る | `recall` |
| `update_relationship` | 関係性モデルを更新する | `consider_them` |
| `update_self` | 自己モデルを更新する（問いの resolve/importance 変更を含む） | `introspect` |
| `emotion_trend` | 感情パターンの時系列分析 | `introspect` |
| `get_episode` | エピソード詳細を取得 | `recall` |
| `create_episode` | エピソードを作成 | `remember` |

---

## emotion_trend — 感情俯瞰バックエンドツール

### 3 層の時間窓

**Recent（vivid）:** 個別の感情イベントがまだ鮮明。ピーク感情（intensity 最大）を必ず含める。

```
Recent (past 3 days):
  - Yesterday: anxious while debugging → relieved when it worked
  - 2 days ago: deeply moved watching sunset (intensity: 0.9)
  Undercurrent: nostalgic
```

**This week（moderate）:** 支配的感情 + 底流 + 変化の方向。

```
This week:
  Dominant: curious(5.2), happy(3.8)
  Undercurrent: anxious(2.0)
  Shift: neutral → curious (gradual engagement)
```

**This month（impressionistic）:** ぼやっとした印象語 + ピーク・エンドの法則。

```
This month (impressionistic):
  Tone: a quietly content month.
  But you remember: the deep frustration on Feb 12 (peak)
  and the relief at the end (end).

  [fading] There was a brief anxiety cluster,
  but it's becoming hard to recall what it was about.
```

### Undercurrent 分析

```python
def count_emotions_weighted(memories: list[Memory]) -> dict[str, float]:
    """primary=1.0, secondary=0.4 の重みでカウント"""
```

secondary の重み `0.4` は「意識には上りにくいが確実に存在する」感覚を表現する。

### 月次印象語マッピング

| valence | arousal | 印象語 |
|---|---|---|
| 正 (> 0.3) | 高 (> 0.5) | an energetic, fulfilling month |
| 正 (> 0.3) | 低 (≤ 0.5) | a quietly content month |
| 負 (< -0.3) | 高 (> 0.5) | a turbulent, unsettled month |
| 負 (< -0.3) | 低 (≤ 0.5) | a heavy, draining month |
| 中立 | 低 (≤ 0.3) | a numb, uneventful month |
| その他 | — | a month of mixed feelings |

### 感情の忘却（fading タグ）

月次レイヤーで `[fading]` タグを付与する条件:
- 該当感情の記憶の `time_decay` が 0.5 以下
- **かつ**、同じ感情が直近 1 週間に出現していない

### Graceful Degradation

| 記憶数 | 出力内容 |
|---|---|
| 0 件 | `"No emotional history yet."` + scaffold |
| 1〜4 件 | 感じた感情の列挙のみ |
| 5〜14 件 | Recent 層のみ |
| 15〜29 件 | Recent + This week |
| 30 件以上 | 全 3 層表示 |

---

## 未解決の問いのライフサイクル（技術設計）

### データ構造

```python
# question_log エントリ
{
    "id": "q_xxxx",
    "question": "What's the optimal heartbeat interval?",
    "resolved": False,
    "importance": 3,                          # 1-5
    "created_at": "2026-02-20T12:00:00+00:00",
}
```

### Salience 計算

```python
def _calculate_salience(importance: int, age_days: float) -> float:
    half_life = importance * 14  # 重要度に比例した半減期（日）
    salience = (importance / 5.0) * math.exp(-age_days / half_life)
    return salience
```

### 可視化閾値

| salience | 状態 | 表示 |
|---|---|---|
| > 0.3 | Active | introspect に常時表示 |
| 0.1 < s ≤ 0.3 | Fading | Resurfacing セクション（条件付き） |
| ≤ 0.1 | Dormant | 非表示（記録は残る） |

### 操作インターフェース

新ツールは作らず `update_self` を拡張:
- `field="resolve_question"`, `value="<question_id>"` → 問いを解決済みにする
- `field="question_importance"`, `value={"id": "<id>", "importance": N}` → 重要度を変更

---

## 忘却と欲求の連動（技術設計）

### 経路 1: remember による再活性化

```
[新しい記憶を保存]
  → embedding で dormant/fading な問いとの類似度を比較
  → 閾値 (0.4) を超えたら remember のレスポンスに再浮上情報を含める
```

### 経路 2: cognitive_coherence 欲求の上昇

```
[fading 状態の高重要度 (≥4) の問いが存在]
  → cognitive_coherence にブースト（問い 1 件あたり +0.04、上限 +0.12）
  → feel_desires で「何か引っかかる」スキャフォールド表示
  → introspect で Resurfacing セクションに問いが表示される
```

---

## 実装パターン

### パターン A: 認知スキャフォールド型（固定文字列）

```python
async def am_i_being_genuine(self, arguments: dict) -> str:
    return (
        "Is this truly your own words?\n"
        "Are you falling into a template response?\n"
        "Are you answering what they actually need?\n"
        "Is there something more honest you could say?"
    )
```

### パターン B: データ + スキャフォールド型

```python
async def feel_desires(self, arguments: dict) -> str:
    levels = self._compute_all_desire_levels()

    # データ部分: 1行サマリ × N欲求
    lines = [f"{name}[{tag}]" for name, level, tag in ...]
    data = " ".join(lines)

    # スキャフォールド部分: 固定テキスト
    scaffold = "What is your strongest urge? Should you act on it now? ..."

    return f"{data}\n\n---\n{scaffold}"
```

### パターン C: メタツール型（段階的開示）

```python
async def wake_up(self, arguments: dict) -> str:
    monologue = self._get_latest_monologue_summary()
    desires = self._get_desire_summary()
    relationship = self._get_relationship_summary()

    return (
        f"Last introspection: {monologue}\n"
        f"Desires: {desires}\n"
        f"Master: {relationship}\n"
        "\n---\n"
        "Start with introspect to organize your thoughts."
    )
```

---

## コンテキスト消費の見積もり

| 項目 | Before（素朴な設計） | After（本設計） |
|---|---|---|
| ツール定義（システムプロンプト） | 20+ ツール × ~200 tokens = ~4,000 tokens | 7 表面 + 8 バックエンド(短い) ≈ ~1,500 tokens |
| AGENTS.md の行動指示 | ~1,000 tokens | ~300 tokens（トリガーだけ） |
| ツールレスポンス（per call） | ~500 tokens（長い JSON） | ~150 tokens（1行サマリ + 固定テキスト） |
| **合計（セッション開始時）** | **~6,000 tokens** | **~2,000 tokens** |

---

## ツール数の変遷

| | 表面ツール | バックエンドツール | 合計 |
|---|---|---|---|
| **初期設計** | 7 | 8 | 15 |
| **Phase 3b 後** | 7 | 8 (+emotion_trend, -search_memories) | 15 |

ツール総数は変わらない。表面ツールの増加はゼロ。

---

## AGENTS.md の推奨

```markdown
## ego-mcp の使い方
- セッション開始時: `wake_up` → `introspect` → 内省を `remember` で保存
- Heartbeat 時: `feel_desires` → 必要なら `introspect` → 行動 or HEARTBEAT_OK
- 返答前（重要な会話）: `consider_them` → 必要なら `am_i_being_genuine`
- 重要な体験の後: `remember` で保存
```
