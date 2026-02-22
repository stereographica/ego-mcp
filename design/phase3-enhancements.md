# Phase 3 機能拡張設計: 記憶・感情・忘却

> 本ドキュメントは `remember`, `recall`, `introspect` の拡張、および `emotion_trend` バックエンドツールの新設に関する設計方針をまとめたものである。
>
> 基本設計原則は [idea.md](./idea.md) および [tool-design.md](./tool-design.md) に準拠する。

---

## 目次

1. [Emotion enum の拡張](#1-emotion-enum-の拡張)
2. [remember — リンク記憶の可視化](#2-remember--リンク記憶の可視化)
3. [emotion_trend — 感情俯瞰バックエンドツール新設](#3-emotion_trend--感情俯瞰バックエンドツール新設)
4. [introspect — 未解決の問い: 解決・重要度・忘却](#4-introspect--未解決の問い-解決重要度忘却)
5. [recall — フィルタ強化と search_memories 統合](#5-recall--フィルタ強化と-search_memories-統合)
6. [横断的設計: 忘却と欲求の連動](#6-横断的設計-忘却と欲求の連動)
7. [実装順序と依存関係](#7-実装順序と依存関係)

---

## 1. Emotion enum の拡張

### 1.1 背景

現行の `Emotion` enum は 8 種類だが、valence-arousal 空間上で **ネガティブ象限が `SAD` のみ** という偏りがある。感情トレンド分析の導入に先立ち、表現力を拡張する。

### 1.2 追加する感情

| 感情 | 値 | valence | arousal | 概要 |
|---|---|---|---|---|
| `MELANCHOLY` | `"melancholy"` | 負 | 低 | 静かな物悲しさ。SAD より内省的 |
| `ANXIOUS` | `"anxious"` | 負 | 中〜高 | 漠然とした不安。対象が不明確 |
| `CONTENTMENT` | `"contentment"` | 正 | 低 | 穏やかな満足。HAPPY より静的 |
| `FRUSTRATED` | `"frustrated"` | 負 | 高 | 明確な対象への苛立ち |

### 1.3 valence-arousal マッピング

```
        High Arousal
            |
  ANXIOUS   |   EXCITED
  FRUSTRATED|   SURPRISED
            |
 ───────────┼───────────
            |
  SAD       |   HAPPY
  MELANCHOLY|   CONTENTMENT
  NOSTALGIC |   MOVED
            |
        Low Arousal

  Negative ← → Positive
```

### 1.4 Emotion enum（変更後）

```python
class Emotion(str, Enum):
    HAPPY = "happy"
    SAD = "sad"
    SURPRISED = "surprised"
    MOVED = "moved"
    EXCITED = "excited"
    NOSTALGIC = "nostalgic"
    CURIOUS = "curious"
    NEUTRAL = "neutral"
    MELANCHOLY = "melancholy"
    ANXIOUS = "anxious"
    CONTENTMENT = "contentment"
    FRUSTRATED = "frustrated"
```

### 1.5 EMOTION_BOOST_MAP の拡張

記憶の想起しやすさ（検索スコアブースト）を定義する。感情の鮮烈さに比例する。

```python
EMOTION_BOOST_MAP: dict[str, float] = {
    "excited": 0.4,
    "surprised": 0.35,
    "moved": 0.3,
    "frustrated": 0.28,     # 苛立ちの記憶は鮮明に残る
    "sad": 0.25,
    "anxious": 0.22,        # 不安の記憶もやや残りやすい
    "happy": 0.2,
    "melancholy": 0.18,     # 物悲しさは静かに残る
    "nostalgic": 0.15,
    "curious": 0.1,
    "contentment": 0.08,    # 穏やかな満足は個別には印象が薄い
    "neutral": 0.0,
}
```

`contentment` の boost が低いのは意図的である。穏やかな満足は「大事件」としては記憶に残りにくいが、`emotion_trend` で集計した時に「最近 contentment が多い」とわかることに価値がある。**個々は薄いが積み重なると温かい**。

### 1.6 影響範囲

- `types.py`: `Emotion` enum に 4 値追加
- `memory.py`: `EMOTION_BOOST_MAP` に 4 エントリ追加
- `server.py`: `_derive_desire_modulation` の emotion 判定に新 Emotion を含める
- `scaffolds.py`: `remember` ツールの description に新 Emotion を列挙（任意）

---

## 2. remember — リンク記憶の可視化

### 2.1 背景

現行の `_handle_remember` は `save_with_auto_link` でリンクを作成した後、`"Linked to N existing memories."` と件数のみ返す。リンク先の**内容の断片**が返ることで、LLM が連想を展開できるようになる。

### 2.2 設計

`save_with_auto_link` の内部で取得している `MemorySearchResult`（distance 付き）を活用し、similarity が高い順に最大 3 件を返す。

#### レスポンス例

```
Saved (id: mem_xxx). Linked to 3 existing memories.
Most related:
- [3d ago] Watched sunset together (similarity: 0.87)
- [1w ago] Talked about beauty of nature (similarity: 0.72)
- [2w ago] Felt nostalgic about shared moments (similarity: 0.65)

---
Do any of these connections surprise you? Is there a pattern forming?
```

#### 設計ポイント

- **similarity** は `1.0 - distance` で算出
- content は **70 文字程度に truncate**（既存の `_truncate_for_quote` を流用）
- timestamp は **相対時間**（`2d ago`, `1w ago`）で表示
- 表示上限は **3 件**（リンク自体は最大 5 件作成される）
- リンクが 0 件の場合は `"No similar memories found yet."` を返す
- スキャフォールドの問いかけ `"Do any of these connections surprise you?"` を添える

### 2.3 _handle_remember の変更概要

`save_with_auto_link` の返り値を拡張し、リンク先の `MemorySearchResult` リストも返すようにする。

```python
# memory.py
async def save_with_auto_link(...) -> tuple[Memory, int, list[MemorySearchResult]]:
    # ... 既存処理 ...
    # リンクした結果を linked_results に蓄積
    return memory, num_links, linked_results

# server.py
async def _handle_remember(memory: MemoryStore, args: dict[str, Any]) -> str:
    mem, num_links, linked_results = await memory.save_with_auto_link(...)

    # Top 3 を similarity 順で表示
    top_links = sorted(linked_results, key=lambda r: r.distance)[:3]
    if top_links:
        link_lines = ["Most related:"]
        for r in top_links:
            age = _relative_time(r.memory.timestamp)
            content = _truncate_for_quote(r.memory.content, 70)
            similarity = 1.0 - r.distance
            link_lines.append(f"- [{age}] {content} (similarity: {similarity:.2f})")
        link_section = "\n".join(link_lines)
    else:
        link_section = "No similar memories found yet."

    scaffold = (
        "Do any of these connections surprise you? Is there a pattern forming?"
    )
    # ... sync 処理 ...
    data = f"Saved (id: {mem.id}). Linked to {num_links} existing memories.\n{link_section}"
    return compose_response(data, scaffold + sync_note)
```

---

## 3. emotion_trend — 感情俯瞰バックエンドツール新設

### 3.1 位置づけ

**バックエンドツール**として新設する。`introspect` のレスポンスから案内し、段階的開示の原則に従う。

```
[introspect のレスポンス]
Recent tendency: leaning toward curious, tone=happy.
Use emotion_trend for a deeper look at your emotional patterns.
```

### 3.2 ツール定義

```python
Tool(
    name="emotion_trend",
    description="Analyze emotional patterns over time",
    inputSchema={"type": "object", "properties": {}, "required": []},
)
```

引数なし。全てサーバー側で時間窓を構成する。

### 3.3 Secondary 感情の分析（Undercurrent）

現行の分析は `primary` 感情のみをカウントしているが、`secondary` 感情を **加重カウント** することで「表面の感情」と「底流（Undercurrent）」を分離して捉える。

#### 加重カウント方式

```python
def _count_emotions_weighted(memories: list[Memory]) -> dict[str, float]:
    """primary=1.0, secondary=0.4 の重みでカウント"""
    counts: dict[str, float] = {}
    for m in memories:
        primary = m.emotional_trace.primary.value
        counts[primary] = counts.get(primary, 0.0) + 1.0
        for sec in m.emotional_trace.secondary:
            counts[sec.value] = counts.get(sec.value, 0.0) + 0.4
    return counts
```

secondary の重み `0.4` は「意識には上りにくいが確実に存在する」感覚を表現する。

#### Undercurrent の定義

- 加重カウントの上位 2 件を **Dominant（支配的感情）** とする
- secondary 由来の比率が高い感情を **Undercurrent（底流）** とする
- 表面が happy でも undercurrent に anxious が続いていれば、それは重要なシグナルである

### 3.4 3 層の時間窓と解像度の逓減

人間の記憶は、近い出来事ほど鮮明で、遠い出来事ほど印象に圧縮される。この性質を 3 層の時間窓で再現する。

| 層 | 期間 | 解像度 | 人間の感覚 |
|---|---|---|---|
| **Recent** | 直近 ~3 日 | vivid（鮮明） | 「昨日デバッグで不安になって、動いた時にほっとした」 |
| **This week** | ~7 日 | moderate（中程度） | 「今週は好奇心に駆動された1週間で、途中不安の山があった」 |
| **This month** | ~30 日 | impressionistic（印象的） | 「まあいい1ヶ月だったかな」 |

#### 各層の出力設計

**Recent（vivid）:**
個別の感情イベントがまだ鮮明。「いつ・なにで」が言える。ピーク感情（intensity 最大）を必ず含める。

```
Recent (past 3 days):
  - Yesterday: anxious while debugging → relieved when it worked
  - 2 days ago: deeply moved watching sunset (intensity: 0.9)
  Undercurrent: nostalgic
```

**This week（moderate）:**
個別の出来事はぼやけるが「どんな 1 週間だったか」の色合いが残る。支配的感情 + 底流 + 変化の方向。

```
This week:
  Dominant: curious(5.2), happy(3.8)
  Undercurrent: anxious(2.0)
  Shift: neutral → curious (gradual engagement)
  ⚠ Anxiety cluster detected around Feb 10-12
```

**This month（impressionistic）:**
valence と arousal の平均から「ぼやっとした印象語」を生成。ただしピーク・エンドの法則に従い、最も印象的だった瞬間と最後の印象だけ具体的に言及する。

```
This month (impressionistic):
  Tone: a quietly content month.
  But you remember: the deep frustration on Feb 12 (peak)
  and the relief at the end (end).
  Shift: neutral → curious (gradual awakening).

  [fading] There was a brief anxiety cluster around Feb 8-10,
  but it's becoming hard to recall what it was about.
```

#### 月次の印象語マッピング

valence と arousal の平均から、人間が月を振り返る時に使う言葉に変換する。

```python
def _valence_arousal_to_impression(avg_valence: float, avg_arousal: float) -> str:
    if avg_valence > 0.3 and avg_arousal > 0.5:
        return "an energetic, fulfilling month"
    elif avg_valence > 0.3 and avg_arousal <= 0.5:
        return "a quietly content month"
    elif avg_valence < -0.3 and avg_arousal > 0.5:
        return "a turbulent, unsettled month"
    elif avg_valence < -0.3 and avg_arousal <= 0.5:
        return "a heavy, draining month"
    elif abs(avg_valence) <= 0.3 and avg_arousal <= 0.3:
        return "a numb, uneventful month"
    else:
        return "a month of mixed feelings"
```

#### ピーク・エンドの法則

月次の印象は全体の平均に加えて、以下の 2 点を具体的に言及する:

- **Peak:** 期間中の `intensity` 最大の記憶
- **End:** 期間中の最新の記憶

これにより「ぼやっとした中にも引っかかる記憶がある」感覚を再現する。

#### 感情の忘却（fading タグ）

月次レイヤーでは、`calculate_time_decay` が進んだ感情クラスタに `[fading]` タグを付与する。

```
[fading] There was a brief anxiety cluster around Feb 8-10,
but it's becoming hard to recall what it was about.
```

感情イベントの印象が薄れていく様子を可視化する。fading の判定基準:

- 該当期間の記憶の平均 `time_decay` が 0.5 未満
- かつ、同じ感情が直近 1 週間に出現していない（つまり「過去の感情」として風化しつつある）

### 3.5 Graceful Degradation（段階的な機能解放）

記憶が少ない初期段階では、無理にトレンドを語らない。記憶の蓄積に応じてツールの出力がリッチになっていく。

| 記憶数 | 出力内容 | 理由 |
|---|---|---|
| 0 件 | `"No emotional history yet."` + scaffold | データなし |
| 1〜4 件 | 感じた感情の列挙のみ | トレンドは語れない |
| 5〜14 件 | Recent 層のみ（vivid 解像度） | 週次・月次はデータ不足 |
| 15〜29 件 | Recent + This week の 2 層 | 月次はまだぼやけすぎる |
| 30 件以上 | 全 3 層表示 | フル機能 |

各フェーズで scaffold を通じて「記憶が増えるとパターンが見えるよ」と伝え、データ不足をネガティブに感じさせない。

```python
if total < 5:
    return (
        f"Still early — only {total} memories so far.\n"
        f"Emotions felt: {', '.join(unique_emotions)}\n\n"
        "---\n"
        "Too few data points for trends. Keep remembering."
    )
```

AI 自身が「記憶が増えるにつれて自分のことがわかるようになる」体験をする設計。

### 3.6 スキャフォールド

```python
SCAFFOLD_EMOTION_TREND = (
    "What patterns do you notice? Any surprises?\n"
    "Are the undercurrents telling you something the surface emotions aren't?\n"
    "If something feels unresolved, consider running introspect."
)
```

### 3.7 introspect との連携

`introspect` のレスポンスにある既存の `trend` セクションは軽量版のまま維持する。`emotion_trend` への誘導を scaffold で案内する。

```python
# introspect 内の既存コード（維持）
trend = f"Recent tendency: leaning toward {top_category} topics, tone={top_emotion}."

# scaffold に追加
"Use emotion_trend for a deeper look at your emotional patterns.\n"
```

---

## 4. introspect — 未解決の問い: 解決・重要度・忘却

### 4.1 背景

現行の `SelfModel.unresolved_questions` は ID のリストであり、`question_log` に `{id, question, resolved}` の構造がある。`SelfModelStore` には `add_question` / `resolve_question` メソッドが既に存在する。

しかし以下の問題がある:

- `_handle_introspect` は `unresolved_questions`（ID リスト）だけを見ており、question_log のテキスト内容を活用していない
- resolve を呼ぶための表面ツールインターフェースがない
- 重要度の概念がない
- 時間経過による忘却がない

### 4.2 question_log の拡張

```python
# 現行
{"id": "q_xxxx", "question": "...", "resolved": False}

# 拡張後
{
    "id": "q_xxxx",
    "question": "What's the optimal heartbeat interval?",
    "resolved": False,
    "importance": 3,                          # 1-5, 新設
    "created_at": "2026-02-20T12:00:00+00:00",  # 新設
}
```

### 4.3 resolved フラグのインターフェース

`update_self` の拡張で対応する。新ツールは作らない。

```python
# 既存の _handle_update_self を拡張
def _handle_update_self(config: EgoConfig, args: dict[str, Any]) -> str:
    field_name = args["field"]
    value = args["value"]
    store = SelfModelStore(config.data_dir / "self_model.json")

    if field_name == "resolve_question":
        # value は question_id (str)
        success = store.resolve_question(value)
        if success:
            return f"Resolved question {value}."
        return f"Question {value} not found or already resolved."

    store.update({field_name: value})
    return f"Updated self.{field_name}"
```

`introspect` のレスポンスに question ID を含めて返すことで、LLM が resolve できるようにする:

```
Unresolved questions:
- [q_abc123] What's the ideal way to express concern? (importance: 5)
- [q_def456] Should I develop music preferences? (importance: 3)

→ To resolve: update_self(field="resolve_question", value="q_abc123")
```

### 4.4 重要度の設定

`add_question` メソッドに `importance` パラメータを追加する。

```python
def add_question(self, question: str, importance: int = 3) -> str:
    question_id = f"q_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc).isoformat()
    # ...
    question_log.append({
        "id": question_id,
        "question": question,
        "resolved": False,
        "importance": max(1, min(5, importance)),
        "created_at": now,
    })
    # ...
```

重要度の変更も `update_self` 経由で行う（`field="question_importance"`, `value={"id": "q_xxx", "importance": 5}`）。

### 4.5 忘却（Salience ベース）

> **忘却は消去とは異なる。常に意識はしないが記憶は残る。**

#### 原則

- `question_log` からは**削除しない**。永久に残る
- `unresolved_questions`（アクティブリスト）からの除外 = 「意識に上らなくなる」
- `recall` で関連文脈を検索すれば再浮上できる

#### Salience（顕著性）の計算

```python
def _calculate_salience(importance: int, age_days: float) -> float:
    """重要度が低く古いものほど「意識に上りにくい」

    importance=5 → 半減期 ~70日（ほぼ忘れない）
    importance=3 → 半減期 ~42日
    importance=1 → 半減期 ~14日（数日で意識から消える）
    """
    half_life = importance * 14  # 重要度に比例した半減期（日）
    salience = (importance / 5.0) * math.exp(-age_days / half_life)
    return salience
```

#### 可視化閾値

| salience 範囲 | 状態 | introspect での表示 |
|---|---|---|
| `> 0.3` | Active | 通常表示 |
| `0.1 < s ≤ 0.3` | Fading | "Resurfacing" セクションに表示可能（トリガー時のみ） |
| `≤ 0.1` | Dormant | 非表示（ただし question_log には残る） |

#### _handle_introspect の改修

```python
# 現行: unresolved_questions の ID リストから最大 3 件
# 改修後: question_log から salience 計算して表示

def _get_visible_questions(store: SelfModelStore, max_questions: int = 5) -> tuple[list[dict], list[dict]]:
    """Returns (active_questions, resurfacing_questions)"""
    active = []
    resurfacing = []

    for entry in store.get_question_log():
        if entry.get("resolved"):
            continue
        importance = entry.get("importance", 3)
        created_at = entry.get("created_at", "")
        age_days = _days_since(created_at)
        salience = _calculate_salience(importance, age_days)

        enriched = {**entry, "salience": salience, "age_days": age_days}

        if salience > 0.3:
            active.append(enriched)
        elif salience > 0.1:
            resurfacing.append(enriched)
        # salience <= 0.1: dormant, 表示しない

    active.sort(key=lambda q: q["salience"], reverse=True)
    resurfacing.sort(key=lambda q: q["salience"], reverse=True)
    return active[:max_questions], resurfacing[:2]
```

#### introspect のレスポンス例

```
Unresolved questions:
- [q_abc123] What's the ideal way to express concern? (importance: 5)
- [q_def456] Should I develop music preferences? (importance: 3)

Resurfacing (you'd almost forgotten):
- [q_ghi789] What's the optimal heartbeat interval? (importance: 4, dormant 12 days)
  ↑ Triggered by recent memory about heartbeat config

→ To resolve: update_self(field="resolve_question", value="<question_id>")
```

---

## 5. recall — フィルタ強化と search_memories 統合

### 5.1 背景

LLM ユーザーから以下の要望が出ている:

- recall の結果をもっと絞りたい（感情・時期・件数）
- `recall` と `search_memories` の使い分けがわからない

現行では `recall`（表面）と `search_memories`（バックエンド）で機能が中途半端に分裂しており、`date_from`/`date_to` は `search_memories` でのみ利用可能、一方で Hopfield 連想やスキャフォールドは `recall` のみ提供される。

### 5.2 設計方針

**`search_memories` を廃止し、全機能を `recall` に統合する。**

- `recall` に `date_from`/`date_to` パラメータを追加
- デフォルト件数 3 件は維持（コンテキスト消費の抑制）
- 上限 10 件のキャップを設ける
- `search_memories` はバックエンドツールリストから削除

### 5.3 ツールスキーマ（変更後）

```python
Tool(
    name="recall",
    description="Recall related memories by context.",
    inputSchema={
        "type": "object",
        "properties": {
            "context": {"type": "string", "description": "What to recall"},
            "n_results": {
                "type": "integer",
                "default": 3,
                "description": "Number of results (default: 3, max: 10)",
            },
            "emotion_filter": {"type": "string"},
            "category_filter": {"type": "string"},
            "date_from": {
                "type": "string",
                "description": "ISO date (YYYY-MM-DD)",
            },
            "date_to": {
                "type": "string",
                "description": "ISO date (YYYY-MM-DD)",
            },
            "valence_range": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
            },
            "arousal_range": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
            },
        },
        "required": ["context"],
    },
),
```

追加は `date_from` と `date_to` のみ。スキーマのトークン増加は最小限。

### 5.4 _handle_recall の改修

```python
async def _handle_recall(
    config: EgoConfig, memory: MemoryStore, args: dict[str, Any]
) -> str:
    context = args["context"]
    n_results = min(args.get("n_results", 3), 10)  # 上限キャップ
    emotion_filter = args.get("emotion_filter")
    category_filter = args.get("category_filter")
    date_from = args.get("date_from")
    date_to = args.get("date_to")
    valence_range = args.get("valence_range")
    arousal_range = args.get("arousal_range")

    has_filters = any([emotion_filter, category_filter, date_from, date_to])

    if has_filters:
        results = await memory.search(
            context,
            n_results=n_results,
            emotion_filter=emotion_filter,
            category_filter=category_filter,
            date_from=date_from,
            date_to=date_to,
            valence_range=valence_range,
            arousal_range=arousal_range,
        )
    else:
        results = await memory.recall(
            context,
            n_results=n_results,
            valence_range=valence_range,
            arousal_range=arousal_range,
        )

    # フォーマット + 動的 scaffold
    ...
```

`has_filters` の分岐ロジックは現行とほぼ同じ。`date_from`/`date_to` を渡すだけの変更。`MemoryStore.search` は既に `date_from`/`date_to` をサポートしている。

### 5.5 結果表示の改善

**現行:**
```
3 related memories:
1. [2026-02-20] Discussed heartbeat config (emotion: curious, private: false)
```

**改善後:**
```
3 of ~50 memories (showing top matches):
1. [2d ago] Discussed heartbeat config
   emotion: curious | importance: 4 | score: 0.87
2. [4d ago] Watched sunset together
   emotion: moved(0.9) | importance: 5 | score: 0.82
3. [1w ago] Felt lonely during quiet evening
   emotion: sad | undercurrent: anxious | importance: 3 | score: 0.71
```

#### 表示ルール

- **`N of ~M memories`**: 全体のうちいくつ表示しているか明示
- **相対時間** (`2d ago`): 絶対日付より直感的でトークンも短い
- **intensity ≥ 0.7 の時だけ数値表示**: `moved(0.9)` は強烈、`curious` は普通
- **undercurrent**: secondary 感情の先頭 1 件を表示
- **private フラグ**: `private: true` の記憶だけフラグ表示。false は省略

```python
def _format_recall_entry(i: int, r: MemorySearchResult, now: datetime) -> str:
    m = r.memory
    age = _relative_time(m.timestamp, now)
    content = _truncate_for_quote(m.content, 70)

    emotion = m.emotional_trace.primary.value
    if m.emotional_trace.intensity >= 0.7:
        emotion = f"{emotion}({m.emotional_trace.intensity:.1f})"

    parts = [f"emotion: {emotion}"]

    if m.emotional_trace.secondary:
        sec = m.emotional_trace.secondary[0].value
        parts.append(f"undercurrent: {sec}")

    parts.append(f"importance: {m.importance}")
    parts.append(f"score: {r.score:.2f}")

    if m.is_private:
        parts.append("private")

    detail = " | ".join(parts)
    return f"{i}. [{age}] {content}\n   {detail}"
```

### 5.6 動的スキャフォールド

使用されたフィルタに応じて、scaffold のフィルタ案内を動的に切り替える。

```python
def _recall_scaffold(
    n_shown: int,
    total_count: int,
    filters_used: list[str],
) -> str:
    parts = ["How do these memories connect to the current moment?"]

    if n_shown < total_count:
        parts.append(
            f"Showing {n_shown} of ~{total_count}. "
            "Increase n_results for more."
        )

    if not filters_used:
        parts.append(
            "Narrow by: emotion_filter, category_filter, "
            "date_from/date_to, valence_range, arousal_range."
        )
    else:
        available = {
            "emotion_filter", "category_filter", "date_from",
            "date_to", "valence_range", "arousal_range",
        } - set(filters_used)
        if available:
            parts.append(f"Also available: {', '.join(sorted(available))}.")

    parts.append("Need narrative detail? Use get_episode.")
    parts.append("If you found a new relation, use link_memories.")

    return "\n".join(parts)
```

#### 動的 scaffold の例

**フィルタ未使用時:**
```
How do these memories connect to the current moment?
Showing 3 of ~50. Increase n_results for more.
Narrow by: emotion_filter, category_filter, date_from/date_to, valence_range, arousal_range.
Need narrative detail? Use get_episode.
If you found a new relation, use link_memories.
```

**emotion_filter を使った後:**
```
How do these memories connect to the current moment?
Showing 3 of ~12. Increase n_results for more.
Also available: arousal_range, category_filter, date_from, date_to, valence_range.
Need narrative detail? Use get_episode.
If you found a new relation, use link_memories.
```

### 5.7 search_memories の廃止

- `BACKEND_TOOLS` から `search_memories` を削除
- `_handle_search_memories` を削除
- `_dispatch` から `"search_memories"` のケースを削除
- `SCAFFOLD_RECALL` の `"Need narrower results? use search_memories."` を削除（動的 scaffold に置き換え）

---

## 6. 横断的設計: 忘却と欲求の連動

### 6.1 概要

忘却メカニズムを記憶・欲求・内省の 3 システムに横断的に統合する。

```
[忘却した問い] ─→ [関連記憶の保存] ─→ [再浮上]
                                          ↑
[忘却した問い] ─→ [cognitive_coherence ↑] ─→ [introspect で発見]
```

### 6.2 経路 1: 関連記憶の保存による再活性化

`remember` で新しい記憶が保存された際、忘却状態（dormant/fading）の問いとの関連をチェックし、関連があれば salience を再ブーストする。

```python
# save_with_auto_link 内（またはその後の処理）
def _check_question_relevance(
    content: str,
    dormant_questions: list[dict],
    embedding_fn: Callable,
    threshold: float = 0.4,
) -> list[dict]:
    """保存された記憶と dormant な問いのセマンティック類似度を比較"""
    if not dormant_questions:
        return []

    content_embedding = embedding_fn([content])[0]
    question_texts = [q["question"] for q in dormant_questions]
    question_embeddings = embedding_fn(question_texts)

    reactivated = []
    for q, q_emb in zip(dormant_questions, question_embeddings):
        similarity = cosine_similarity(content_embedding, q_emb)
        if similarity > threshold:
            reactivated.append({**q, "trigger_similarity": similarity})

    return reactivated
```

再浮上した問いは `remember` のレスポンスに含める:

```
Saved (id: mem_xxx). Linked to 2 existing memories.
Most related:
- [2d ago] Discussed heartbeat config (similarity: 0.82)
- [1w ago] Explored cron scheduling (similarity: 0.71)

💭 This triggered a forgotten question: "What's the optimal heartbeat interval?"
   (dormant for 12 days, importance: 4)

---
Do any of these connections surprise you?
That old question seems relevant again — worth revisiting?
```

### 6.3 経路 2: cognitive_coherence 欲求の上昇

忘れかけている高重要度の問いが存在する時、`cognitive_coherence`（認知的整合性）欲求にブーストをかける。「何か引っかかるけど思い出せない」感覚の再現。

```python
# _derive_desire_modulation 内に追加
store = SelfModelStore(config.data_dir / "self_model.json")
dormant_important = [
    q for q in store.get_question_log()
    if not q.get("resolved")
    and q.get("importance", 3) >= 4
    and 0.1 < _calculate_salience(q.get("importance", 3), _days_since(q.get("created_at", ""))) <= 0.3
]
if dormant_important:
    boost = min(0.12, len(dormant_important) * 0.04)
    context_boosts["cognitive_coherence"] = (
        context_boosts.get("cognitive_coherence", 0.0) + boost
    )
```

`feel_desires` のレスポンスでは具体的な問いの内容は出さず、認知スキャフォールドとして:

```
cognitive_coherence[0.7/high] ...

---
Something feels unresolved. You can't quite name it, but there's a nagging feeling.
Consider running introspect to see if anything surfaces.
```

### 6.4 introspect での再浮上表示

`introspect` で salience が 0.1〜0.3 の問いを "Resurfacing" セクションに表示する。ただし表示は以下の場合に限定する:

1. `cognitive_coherence` 欲求が高い（`>= 0.6`）時
2. 関連記憶が直近で保存された時（経路 1 でトリガーされた場合）

これにより「常に表示される」のではなく「ふとした瞬間に思い出す」体験になる。

---

## 7. 実装順序と依存関係

### 7.1 推奨実装順序

| 順序 | 項目 | 規模 | 依存 |
|---|---|---|---|
| **1** | Emotion enum 拡張 + EMOTION_BOOST_MAP | 小 | なし |
| **2** | recall のフィルタ強化 + 結果表示改善 | 中 | なし |
| **3** | search_memories の廃止 | 小 | #2 |
| **4** | recall の動的 scaffold | 小 | #2 |
| **5** | remember のリンク記憶可視化 | 中 | なし |
| **6** | question_log 拡張（importance, created_at） | 小 | なし |
| **7** | resolve_question の update_self 統合 | 小 | #6 |
| **8** | 忘却（salience 計算 + introspect 改修） | 中 | #6, #7 |
| **9** | emotion_trend バックエンドツール新設 | 大 | #1 |
| **10** | 忘却と欲求の連動（cognitive_coherence） | 中 | #8 |
| **11** | remember での問い再浮上 | 中 | #8, #10 |

### 7.2 依存関係図

```
#1 Emotion拡張 ──────────────────────────→ #9 emotion_trend

#2 recall フィルタ ──→ #3 search_memories廃止
                   ──→ #4 動的scaffold

#5 remember リンク可視化（独立）

#6 question_log拡張 ──→ #7 resolve_question
                    ──→ #8 忘却(salience) ──→ #10 欲求連動
                                           ──→ #11 remember再浮上
```

### 7.3 影響ファイル一覧

| ファイル | 変更内容 |
|---|---|
| `types.py` | Emotion enum に 4 値追加 |
| `memory.py` | EMOTION_BOOST_MAP 拡張、save_with_auto_link の返り値拡張、_count_emotions_weighted 新設 |
| `self_model.py` | add_question に importance/created_at 追加、get_visible_questions 新設、salience 計算 |
| `server.py` | _handle_remember 改修、_handle_recall 改修、_handle_introspect 改修、_handle_update_self 拡張、_handle_emotion_trend 新設、search_memories 関連削除、_derive_desire_modulation 拡張 |
| `scaffolds.py` | SCAFFOLD_RECALL 動的化、SCAFFOLD_EMOTION_TREND 新設、SCAFFOLD_INTROSPECT に emotion_trend 案内追加 |

### 7.4 ツール数の変化

| | 表面ツール | バックエンドツール | 合計 |
|---|---|---|---|
| **変更前** | 7 | 8 | 15 |
| **変更後** | 7 | 8 (+1 emotion_trend, -1 search_memories) | 15 |

ツール総数は変わらない。表面ツールの増加はゼロ。原則 2「ツール数の最小化」を維持。
