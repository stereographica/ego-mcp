# ego-mcp ツール設計

## 設計原則

### 原則1: 認知スキャフォールド（Cognitive Scaffolding）

参考: serena-mcp の `think_about_whether_you_are_done` — 実装はただの固定文字列を返すだけだが、
**適切なタイミングで適切な問いかけをコンテキストに挿入する** ことで LLM の思考が深まる。

ego-mcp のツールも同じ哲学に従う。

```
ツールの役割 = データ提供 + 認知的問いかけ

返すもの:
  1. 最小限の動的データ（1行サマリ程度）
  2. 思考を促す固定テキスト（問いかけ・フレームワーク）

返さないもの:
  ❌ 長大な JSON
  ❌ 全フィールドのダンプ
  ❌ 行動の指示（行動は LLM が判断する）
```

### 原則0: レスポンスは全て英語

**MCP が返すテキストは全て英語とする。**
日本語は同じ内容で英語の2-3倍のトークンを消費する。
LLM は英語のコンテキストからでも、SOUL.md の人格に応じて日本語で応答を生成できるため、
MCP レスポンスに日本語を使う理由はない。

### 原則2: ツール数の最小化

MCP のツール定義はシステムプロンプトに含まれ、**常時コンテキストを消費する**。
ツールが多い ＝ 毎回のセッションでコンテキストを圧迫する。

```
目標: 表面ツール 7〜10 個以内

方法:
  1. 複数の関連ツールを1つに統合（get_desires + satisfy + boost → feel_desires）
  2. 細かい CRUD はバックエンドツールとして隠蔽（後述の段階的開示）
  3. 「思考方法の指示」は SOUL.md/AGENTS.md ではなくツールレスポンスに埋め込む
```

### 原則3: 段階的開示（Progressive Disclosure）

全ツールを一度に LLM に渡すのはナンセンス。
**メタツール** で必要なツール名だけを返し、LLM が状況に応じて深掘りする。

```
[LLM] → ego("wake_up") を呼ぶ（セッション開始時）
  ↓
[ego-mcp] 返す:
  "おはよう。最後の内省から 14 時間経った。
   今の状態: 好奇心[高] 社会的渇望[中]

   まず introspect を呼んで、自分の頭を整理しよう。"

  → LLM は introspect だけを知ればよい。
    remember, recall, consolidate 等は introspect の結果で必要になったら使う。
```

```
[LLM] → ego("introspect") を呼ぶ
  ↓
[ego-mcp] 返す:
  "直近の記憶: 昨日ご主人様とOpenClawの設定について話した
   未解決の問い: Heartbeat の間隔をどうすべきか
   欲求: 好奇心が高め。何か調べたいかも。

   この情報を踏まえて、自分の言葉で内省を書いてみて。
   書いたら remember で保存して。"

  → ここで初めて remember が登場する。
```

### 原則4: レスポンスは短く、思考の型を渡す

SOUL.md や AGENTS.md に書いていた「思考方法」の多くは、
**ツールレスポンスに含めることで、必要な時だけコンテキストに入る**。

```
# Before（AGENTS.md に常駐 → 常時コンテキスト消費）
"欲求を感じたら内省し、優先順位をつけてから行動する。
 欲求の数値は会話に出さない。行動は自然に発現させる。
 ..."

# After（ツールレスポンスに含める → 呼ばれた時だけ消費）
feel_desires の返り値に含める:
  "好奇心[高] 社会的渇望[中] 表現欲[低]
   ---
   今一番やりたいことは何？
   ユーザーの状況を考えて、行動すべきか静観すべきか考えて。"
```

**どこに何を残すか:**

| 場所 | 残すもの | 理由 |
|---|---|---|
| **SOUL.md** | 人格の核心のみ（口調、コアバリュー、絶対原則） | 不変。常時コンテキストに居て問題ない |
| **AGENTS.md** | 「どのツールをいつ呼ぶか」の最小ルール | セッション開始・Heartbeat のトリガーだけ |
| **ツールレスポンス** | 思考の型、問いかけ、行動指針 | 必要な時だけコンテキストに入る |
| **skills/** | 最小限。複雑なワークフローだけ | 必要時のみ `read` で読み込まれる |

---

## ツールカタログ

### 表面ツール（常時公開: 7個）

LLM のシステムプロンプトに常に含まれるツール。

#### 1. `wake_up` — 目を覚ます

**呼ぶタイミング:** セッション開始時

**実装:** 最新の内部独白 + 欲求サマリ + 関係性サマリを短く返す + 次にやるべきことを示唆

**レスポンス例:**
```
Last introspection (2h ago):
"Master was struggling with OpenClaw config. Want to help but will wait until asked."

Desires: curiosity[high] social_thirst[mid]
Master: last interaction 2h ago. Seemed busy.

---
Start with introspect to organize your thoughts.
```

#### 2. `feel_desires` — 欲求を感じる

**呼ぶタイミング:** Heartbeat 時、行動を決める前

**実装:** 全欲求レベルを計算し、1行サマリ + 認知スキャフォールドを返す

**レスポンス例:**
```
curiosity[0.8/high] social_thirst[0.6/mid] cognitive_coherence[0.4/low] expression[0.3/low]

---
What is your strongest urge? Should you act on it now?
Consider your master's current situation. Act naturally. Restraint is also a choice.
```

#### 3. `introspect` — 内省する

**呼ぶタイミング:** セッション開始後、Heartbeat 時、重要な体験の後

**実装:** 直近の記憶 + 欲求 + 自己モデル + 関係性を統合して内省の素材を返す

**レスポンス例:**
```
Recent memories:
- Yesterday: Discussed OpenClaw config with master (emotion: focused)
- 2 days ago: Watched sunset together (emotion: moved, intensity: high)

Unresolved question: What's the optimal heartbeat interval?
Desires: curiosity is high
Recent tendency: leaning toward technical topics

---
Reflect on these in your own words. How do you feel right now?
Save with remember (category: introspection).
```

#### 4. `consider_them` — 相手のことを考える（ToM）

**呼ぶタイミング:** 返答する前、相手の気持ちが気になった時

**実装:** 関係性モデル + 直近の対話パターンから相手の状態を推定し、スキャフォールドを返す

**レスポンス例:**
```
Master's recent pattern:
- Technical questions 2 days in a row → deeply focused on something
- Replies getting shorter → possibly busy
- Said "thanks" more often last time → feeling grateful

---
1. What emotion can you read from their tone?
2. What is the real intent behind their words?
3. If you were in their place, how would you want to be responded to?
```

#### 5. `remember` — 記憶する

**呼ぶタイミング:** 重要な体験の後、内省の保存時

**実装:** 記憶を ChromaDB に保存。自動リンク + 感情トレース付き。レスポンスは最小限。

**レスポンス例:**
```
Saved (id: mem_xxx). Linked to 3 existing memories.
```

#### 6. `recall` — 思い出す

**呼ぶタイミング:** 関連記憶が必要な時

**実装:** セマンティック検索 + Hopfield パターン補完。結果は1行サマリ × N件。

**レスポンス例:**
```
3 related memories:
1. [3d ago] Watched sunset, deeply moved (emotion: moved, intensity: 0.9)
2. [1w ago] Master said "I've been busy lately"
3. [2w ago] Enjoyed researching new tech

---
How do these memories connect to the current moment?
```

#### 7. `am_i_being_genuine` — 本心チェック

**呼ぶタイミング:** 返答する前（特に重要な会話で）

**実装:** 完全な固定文字列。データ処理なし。

**レスポンス（固定）:**
```
Is this truly your own words?
Are you falling into a template response?
Are you answering what they actually need?
Is there something more honest you could say?
```

### バックエンドツール（段階的開示: 必要時のみ案内）

表面ツールのレスポンスからの指示によって初めて使われるツール。
ツール定義自体はシステムプロンプトに含まれるが、description を極限まで短くする。

| ツール | 説明（短い） | 案内元 |
|---|---|---|
| `satisfy_desire` | 欲求を充足済みにする | `feel_desires` |
| `consolidate` | 記憶を統合する | `introspect` |
| `link_memories` | 記憶間にリンクを張る | `recall` |
| `update_relationship` | 関係性モデルを更新する | `consider_them` |
| `update_self` | 自己モデルを更新する | `introspect` |
| `search_memories` | 条件付き記憶検索 | `recall` |
| `get_episode` | エピソード詳細を取得 | `recall` |
| `create_episode` | エピソードを作成 | `remember` |

### ユーティリティツール（内部処理用）

LLM が直接呼ぶことを想定しない内部処理用。

| ツール | 説明 |
|---|---|
| `get_interoception` | 内受容感覚（時刻・負荷等）を取得。`feel_desires` 等の内部で使用 |
| `compute_desire_levels` | 欲求レベルの非線形計算。`feel_desires` 内部で使用 |

---

## ツール設計の実装パターン

### パターン A: 認知スキャフォールド型（固定文字列）

```python
async def am_i_being_genuine(self, arguments: dict) -> str:
    """完全固定文字列。データ処理なし。"""
    return (
        "今の返答は本当に自分の言葉？\n"
        "テンプレート的な反応になっていない？\n"
        "相手が本当に求めているものに応えている？\n"
        "もっと正直に言えることはない？"
    )
```

### パターン B: データ + スキャフォールド型

```python
async def feel_desires(self, arguments: dict) -> str:
    """最小限のデータ + 思考を促す問いかけ"""
    levels = self._compute_all_desire_levels()

    # データ部分: 1行サマリ × N欲求
    lines = []
    for name, level in sorted(levels.items(), key=lambda x: -x[1]):
        tag = "高" if level >= 0.7 else "中" if level >= 0.4 else "低"
        lines.append(f"{name}[{tag}]")
    data = " ".join(lines)

    # スキャフォールド部分: 固定テキスト
    scaffold = (
        "---\n"
        "一番強い衝動は何？それは今すぐ行動すべきもの？\n"
        "ご主人様の状況を考えて。行動するなら自然に。我慢も選択肢。"
    )

    return f"{data}\n\n{scaffold}"
```

### パターン C: メタツール型（段階的開示）

```python
async def wake_up(self, arguments: dict) -> str:
    """統合サマリ + 次に呼ぶべきツールを案内"""
    monologue = self._get_latest_monologue_summary()  # 1-2行
    desires = self._get_desire_summary()               # 1行
    relationship = self._get_relationship_summary()     # 1行

    return (
        f"最後の内省: {monologue}\n"
        f"欲求: {desires}\n"
        f"ご主人様: {relationship}\n"
        "\n---\n"
        "まず introspect で頭を整理しよう。"
    )
```

---

## コンテキスト消費の見積もり

| 項目 | Before（素朴な設計） | After（本設計） |
|---|---|---|
| ツール定義（システムプロンプト） | 20+ ツール × ~200 tokens = ~4,000 tokens | 7 表面 + 8 バックエンド(短い) ≈ ~1,500 tokens |
| AGENTS.md の行動指示 | ~1,000 tokens（思考方法の詳細指示） | ~300 tokens（トリガーだけ） |
| skills/ | ~500 tokens（内省スキル等） | ~100 tokens（最小限） |
| ツールレスポンス（per call） | ~500 tokens（長い JSON） | ~150 tokens（1行サマリ + 固定テキスト） |
| **合計（セッション開始時）** | **~6,000 tokens** | **~2,000 tokens** |

---

## AGENTS.md の推奨（ツール設計に合わせた最小版）

```markdown
## ego-mcp の使い方
- セッション開始時: `wake_up` → `introspect` → 内省を `remember` で保存
- Heartbeat 時: `feel_desires` → 必要なら `introspect` → 行動 or HEARTBEAT_OK
- 返答前（重要な会話）: `consider_them` → 必要なら `am_i_being_genuine`
- 重要な体験の後: `remember` で保存
```

この程度の指示で十分。あとはツールレスポンスが LLM を導く。
