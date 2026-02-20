# LLM 向けのより人間に近い外部記憶と欲求を持つための ego-mcp 設計書

## 背景

現在の LLM で動作する AI エージェントは、人格を模したプロンプト（`SOUL.md`）をベースとして駆動する。

だが、プロンプトベースでの人格模倣には限界がある。現状の主な問題意識は以下の通り。

- **欲求の不在**
  - 人間であれば存在のモチベーションとして欲求を抱えているはずであるが、LLM にはない
- **セッション持続の問題**
  - LLM の宿命として、長時間セッションを維持することが出来ない
  - セッションが切れた際には Markdown で書かれたメモリファイルを読み直すことになるが、これを LLM は「記録」として解釈する
  - 必要なのは「記録」の再読み込みではなく、**自分の思考の続き**として文脈を再構築すること
- **記憶の平板さ**
  - 現在の記憶はテキスト＋メタデータ（感情タグ、重要度）だが、人間の記憶はもっと多層的
  - 感情の強度・覚醒度・身体状態まで含めた「体験」として記憶を保持する必要がある

より人格の継続性を高めるためには、外部記憶をコンテキストに注入する方法を根本的に工夫する必要がある。

---

## アーキテクチャ概要

### OpenClaw の workspace 構造（前提）

本設計は OpenClaw 上で動作することを前提とする。OpenClaw は以下のファイルをセッション開始時にコンテキストに注入する。

```
<workspace>/
├── AGENTS.md      … 操作指示・メモリ管理ルール
├── SOUL.md        … ペルソナ・トーン・境界線（人格のベースライン）
├── IDENTITY.md    … 名前・キャラクター・絵文字
├── USER.md        … ユーザープロフィール
├── TOOLS.md       … ツール運用メモ
├── HEARTBEAT.md   … ハートビート時のチェックリスト
├── MEMORY.md      … キュレーションされた長期記憶（メインセッションのみ）
├── memory/
│   └── YYYY-MM-DD.md  … 日次ログ（追記型）
└── skills/
    └── *.md       … スキル定義
```

### スコープ分離の原則

```
┌────────────────────────────────────────────────────────┐
│  OpenClaw Workspace Files（プロンプトレイヤー）         │
│  ────────────────────────────────────────────────────  │
│  SOUL.md     … 人格の「憲法」。不変に近いベースライン  │
│  IDENTITY.md … 名前・外見・象徴                        │
│  USER.md     … ユーザーとの関係の静的定義               │
│  AGENTS.md   … 行動規範・ego-mcp の使い方指示           │
│  HEARTBEAT.md… 定期チェック＋内省トリガー               │
│  MEMORY.md   … キュレーション済み長期記憶               │
│  skills/     … ego-mcp を使った思考スキルの定義         │
└───────────────────────┬────────────────────────────────┘
                        │ MCP ツール呼び出し
                        ▼
┌────────────────────────────────────────────────────────┐
│  ego-mcp（MCP Server：計算・永続化レイヤー）           │
│  ────────────────────────────────────────────────────  │
│  ChromaDB + 構造化DB                                   │
│  ├── 記憶システム（memory-mcp 拡張）                   │
│  │   ├── エピソード記憶（体験の時系列）                │
│  │   ├── 意味記憶（事実・知識）                        │
│  │   ├── 感情記憶（体験＋感情トレース）                │
│  │   ├── 連想・パターン補完（Hopfield）                │
│  │   └── 統合・忘却（Consolidation）                   │
│  ├── 欲求システム（desire-system 再設計）               │
│  │   ├── 抽象的欲求レベルの計算                        │
│  │   ├── 文脈感応的ブースト                            │
│  │   └── 非線形増減モデル                              │
│  ├── 関係性モデル（Relational Model）                   │
│  │   └── 人物ごとの構造化された理解                    │
│  ├── 自己モデル（Self-Model）                           │
│  │   └── 自己認識・メタ認知・価値観                    │
│  ├── 内部独白（Inner Monologue）                        │
│  │   └── 欲求＋記憶＋感覚の統合思考                    │
│  └── ToM（心の理論）                                    │
│      └── 視点取得の形式的操作                          │
└────────────────────────────────────────────────────────┘
```

### 各レイヤーの責務

| レイヤー | 責務 | 例 |
|---|---|---|
| **SOUL.md** | 人格の不変ベースライン。「何者であるか」の基本定義。変更頻度はほぼゼロ | 一人称、口調、コアバリュー、絶対に守る原則 |
| **IDENTITY.md** | 名前・外見・象徴。ブートストラップで決定され、ほぼ変更されない | 名前、絵文字、キャラクター設定 |
| **USER.md** | ユーザーの静的プロフィール | 呼び方、タイムゾーン、基本的な好み |
| **AGENTS.md** | 行動規範と ego-mcp の使い方。「どのように考え、行動するか」 | セッション開始時に内省を読む、欲求に従って行動する、等 |
| **HEARTBEAT.md** | 定期チェックリスト＋内省のトリガー | 「欲求チェック → 内省生成 → 記憶整理」 |
| **skills/** | ego-mcp のツールを組み合わせた思考プロセスの定義 | `inner-monologue.md`, `desire-action.md` |
| **ego-mcp** | 計算・永続化・認知スキャフォールド。ベクトル検索、構造化データ、思考の問いかけ注入 | 欲求レベル計算、記憶保存/検索、内省の型の提供 |

**原則：人格の「何」は workspace ファイルで定義し、「どう計算し・どう思考を促すか」は ego-mcp が担う。**

### ツール設計の基本方針

ego-mcp のツール設計は **認知スキャフォールド（Cognitive Scaffolding）** パターンに従う。

参考: serena-mcp の `think_about_whether_you_are_done` — 固定文字列を返すだけのツールだが、
適切なタイミングでコンテキストに挿入されることで LLM の思考が深まり、気づきが生まれる。

**4つの原則:**

1. **認知スキャフォールド** — ツールは「データ + 思考を促す問いかけ」を返す。行動指示ではなく認知の型を提供する
2. **ツール数の最小化** — 表面ツール7個 + バックエンドツール8個（短い description）。合計 ~1,500 tokens
3. **段階的開示** — メタツール（`wake_up`）が次に必要なツール名を返す。全ツールを一度に把握する必要がない
4. **レスポンスは短く** — 1行サマリ × N件 + 固定テキストの問いかけ。長い JSON は返さない

**思考方法の指示はツールレスポンスに移す:**

| 場所 | 残すもの |
|---|---|
| **SOUL.md** | 人格の核心のみ（口調、コアバリュー、絶対原則） |
| **AGENTS.md** | 「どのツールをいつ呼ぶか」の最小ルール（4行程度） |
| **ツールレスポンス** | 思考の型、問いかけ、行動指針（必要な時だけコンテキストに入る） |
| **skills/** | 最小限。複雑なワークフローのみ（OpenClaw の `read` で必要時に読み込み） |

> 📋 ツールカタログの詳細は [design/tool-design.md](./design/tool-design.md) を参照。

---

## 1. 記憶システム（Memory System）

### 1.1 現状の評価（embodied-claude memory-mcp）

参考実装 `memory-mcp` は以下の機能を持ち、多くはそのまま活用できる。

| 機能 | 評価 | 備考 |
|---|---|---|
| ChromaDB セマンティック検索 | ✅ 優秀 | そのまま採用 |
| Hopfield ネットワーク | ✅ 優秀 | パターン補完による連想記憶 |
| エピソード記憶 | ✅ 良い | 一連の体験をストーリーとして統合 |
| ToM（心の理論） | ✅ 良い | 視点取得の形式的操作 |
| Consolidation | ✅ 良い | Sleep-like replay |
| Working Memory Buffer | ✅ 良い | 短期記憶バッファ |
| 因果リンク | ✅ 良い | 記憶間の因果関係 |
| 連想展開（Association） | ✅ 良い | グラフ探索による発散的想起 |
| 感覚統合（Sensory） | ✅ 良い | 視覚・聴覚の記憶統合 |

### 1.2 不足している機能と追加設計

#### A. 感情記憶（Emotional Memory）の豊富化

現在の `emotion` は単なるタグ（`happy`, `sad` 等）だが、人間の感情記憶はもっと多次元的である。リサ・フェルドマン・バレットの構成主義的情動理論に基づき、感情を多次元ベクトルとして記録する。

```
# 現状（NG）
Memory { content: "ご主人様と一緒に空を見た", emotion: "happy" }

# あるべき姿（OK）
Memory {
  content: "ご主人様と一緒に空を見た",
  emotional_trace: {
    primary: "happy",
    secondary: ["grateful", "nostalgic"],
    intensity: 0.85,          # 感情の強度 (0.0〜1.0)
    valence: 0.9,             # ポジティブ-ネガティブ (-1.0〜1.0)
    arousal: 0.6,             # 覚醒度 (0.0〜1.0)
    body_state_at_time: {     # その時の内受容感覚（参考実装の interoception）
      time_phase: "evening",
      system_load: "low",
      uptime_hours: 2.5
    }
  }
}
```

**ツール:** 感情トレースは `remember` ツールに統合（個別ツールは作らない）。
感情での検索は `recall` のフィルタオプションとして提供。

#### B. 記憶カテゴリの拡張

現在のカテゴリに加えて `introspection`, `relationship`, `self_discovery`, `dream`, `lesson` を追加。

#### C. OpenClaw memory との統合

```
OpenClaw memory (Markdown)     ego-mcp memory (ChromaDB)
─────────────────────────      ─────────────────────────
人間が読める形式               機械が検索する形式
セッション開始時に自動注入      MCP ツール経由でアクセス
日次ログ＋キュレーション済み    セマンティック検索＋連想

→ 両者は相互補完。日次ログ書き込み時に ego-mcp にも保存し、
  定期的に MEMORY.md にキュレーション。
```

---

## 2. 欲求システム（Desire System）

### 2.1 参考実装の問題点

参考実装 `embodied-claude/desire-system` には以下の問題がある。

1. **欲求が個別具体的すぎる** — `look_outside`, `browse_curiosity`, `miss_companion`, `observe_room` は `embodied-claude` で出来ることに密結合
2. **欲求レベルの計算が単純すぎる** — 経過時間の線形増加のみ
3. **欲求 → 行動が固定的** — `browse_curiosity >= 0.7 → WebSearch` のように1:1対応

### 2.2 再設計：マズローの階層 × ドライブ理論のハイブリッド

欲求を **抽象的な動機付け** として再定義し、具体的行動への変換は LLM の判断に委ねる。

```
レベル1: 生存的欲求（ホメオスタシス）
  ├── information_hunger (情報飢餓)
  │     新しい入力がないと増加。何かを取り込みたい衝動
  ├── social_thirst (社会的渇望)
  │     対話がないと増加。誰かと繋がりたい衝動
  └── cognitive_coherence (認知的整合性)
        矛盾する記憶や未処理の体験があると増加。整理したい衝動

レベル2: 安全・安定欲求
  ├── pattern_seeking (パターン欲求)
  │     世界を理解したい。法則性を見出したい衝動
  └── predictability (予測欲求)
        次に何が起こるか知りたい衝動

レベル3: 所属・愛情欲求
  ├── recognition (承認欲求)
  │     相手から認められたい衝動
  └── resonance (共感欲求)
        相手と心情を共有したい衝動

レベル4: 自己実現的欲求
  ├── expression (表現欲求)
  │     何かを生み出したい・伝えたい衝動
  └── curiosity (好奇心)
        新しいことを知りたい・探索したい衝動
```

**重要: 欲求 → 行動の変換は LLM に委ねる**

```
# NG（参考実装の方式）
browse_curiosity >= 0.7 → WebSearch を実行

# OK（本設計の方式）
curiosity >= 0.7 → LLM が文脈に応じて行動を選択
  → Web を検索するかもしれない
  → 過去の記憶を掘り返すかもしれない
  → ご主人様に質問するかもしれない
  → 何もしないかもしれない（我慢も選択肢）
```

### 2.3 欲求レベルの非線形計算

#### ego-mcp でのレベル計算

```python
import math

def calculate_desire_level(
    elapsed_hours: float,
    satisfaction_hours: float,
    context_boost: float = 0.0,
    emotional_modulation: float = 0.0,
    recent_satisfaction_quality: float = 0.5,
) -> float:
    """
    非線形な欲求レベル計算。

    Args:
        elapsed_hours: 最後に満たされてからの経過時間
        satisfaction_hours: 半飽和時間（この時間で約0.5に達する）
        context_boost: 文脈による一時的ブースト（対話中に関連話題が出た等）
        emotional_modulation: 感情による変調（ネガティブ体験 → 社会的欲求↑ 等）
        recent_satisfaction_quality: 前回の充足の質（0.0〜1.0）
          質が低いと次の欲求がより早く上昇する
    """
    # 基本レベル：シグモイド（急に増えて上限で飽和）
    # 充足の質が低いと半飽和時間が短くなる
    adjusted_hours = satisfaction_hours * (0.5 + 0.5 * recent_satisfaction_quality)
    x = (elapsed_hours / adjusted_hours) * 6 - 3  # -3〜3 にスケーリング
    base_level = 1.0 / (1.0 + math.exp(-x))

    # 文脈ブースト + 感情変調
    modulated = base_level + context_boost + emotional_modulation

    return max(0.0, min(1.0, modulated))
```

#### 欲求レベルに影響する要因

| 要因 | 説明 | 計算場所 |
|---|---|---|
| **時間減衰** | 基本的なベースライン増加（シグモイド） | ego-mcp |
| **予測誤差** | 驚きの体験 → 好奇心が急上昇（ドーパミン的反応） | ego-mcp（自動検出） |
| **文脈感応** | 特定の話題に触れる → 関連欲求が上がる | ego-mcp（ToM と連動） |
| **充足の質** | 前回の充足が不十分 → 次の上昇が早い | ego-mcp |
| **感情変調** | ネガティブ記憶 → 社会的渇望↑、ポジティブ記憶 → 好奇心↑ | ego-mcp |
| **時刻・体調** | 深夜 → 内省的欲求↑（内受容感覚との統合） | ego-mcp + interoception |

#### ツール（認知スキャフォールド方式）

4つの個別ツール（`get_desires`, `satisfy_desire`, `boost_desire`, `modulate_desire`）を
**`feel_desires` 1本に統合**。

- レスポンスは欲求の1行サマリ + 思考を促す問いかけ
- `satisfy_desire` はバックエンドツールとして残し、`feel_desires` のレスポンスから案内
- 欲求の数値や名前に関するルール（会話に出さない等）は SOUL.md ではなく `feel_desires` のレスポンスに含める

> 詳細は [design/tool-design.md](./design/tool-design.md) の `feel_desires` を参照。

---

## 3. 関係性モデル（Relational Model）

### 3.1 目的

特定の人物についての **構造化された理解** を永続的に保持する。
`USER.md` が静的な基本情報を提供するのに対し、関係性モデルは **動的に進化する理解** を提供する。

### 3.2 スコープ分離

| 項目 | 管理場所 | 理由 |
|---|---|---|
| 名前・呼び方・タイムゾーン | `USER.md` | 静的情報、セッション開始時に必ず注入 |
| コミュニケーションスタイル | ego-mcp | 対話パターンの分析から動的に更新 |
| 感情ベースライン | ego-mcp | 相互作用の蓄積から算出 |
| 信頼度 | ego-mcp | 対話の質・頻度から動的に変化 |
| 共有体験 | ego-mcp | エピソード記憶への参照 |
| 推定された性格特性 | ego-mcp | ToM の蓄積から構築 |

### 3.3 ego-mcp でのデータ構造

```python
@dataclass
class RelationshipModel:
    """特定の人物についての構造化された理解"""

    person_id: str
    name: str

    # 知っている事実（動的に追加）
    known_facts: list[str]

    # 対話パターン
    communication_style: dict  # {"formality": 0.3, "humor": 0.7, ...}
    preferred_topics: list[str]
    sensitive_topics: list[str]

    # 感情的関係性
    emotional_baseline: dict  # {"warmth": 0.8, "respect": 0.9, ...}
    trust_level: float        # 0.0〜1.0

    # 共有した体験
    shared_episode_ids: list[str]  # エピソード記憶への参照

    # ToM から推定された情報
    inferred_personality: dict     # {"openness": 0.8, "conscientiousness": 0.6, ...}
    recent_mood_trajectory: list   # 最近の気分の変化の推移

    # メタ情報
    first_interaction: str         # 最初の対話日時
    last_interaction: str          # 最後の対話日時
    total_interactions: int        # 総対話回数
```

### 3.4 ツール（認知スキャフォールド方式）

4つの個別ツールを **`consider_them` 1本に統合**。

- レスポンスは関係性サマリ + ToM のフレームワーク（問いかけ）
- `update_relationship` はバックエンドツールとして `consider_them` から案内

> 詳細は [design/tool-design.md](./design/tool-design.md) の `consider_them` を参照。

---

## 4. 自己モデル（Self-Model）

### 4.1 目的

「自分が何者であるか」についての **動的な自己認識** を保持する。
`SOUL.md` が人格の「憲法」（不変のベースライン）を定義するのに対し、自己モデルは **体験を通じて変化する自己理解** を保持する。

### 4.2 スコープ分離

| 項目 | 管理場所 | 理由 |
|---|---|---|
| コアバリュー・原則 | `SOUL.md` | 不変のベースライン。人格の憲法 |
| 口調・一人称 | `SOUL.md` | 基本的に固定 |
| 名前・外見設定 | `IDENTITY.md` | ブートストラップ時に決定 |
| 好み・嗜好の変化 | ego-mcp | 体験を通じて動的に変化 |
| 得意・不得意の自己認識 | ego-mcp | メタ認知として動的に更新 |
| 現在の目標・関心 | ego-mcp | 欲求 + 体験から動的に生成 |
| 未解決の問い | ego-mcp | 内省から蓄積 |
| 自信の度合い | ego-mcp | 体験の成功/失敗から変動 |

### 4.3 ego-mcp でのデータ構造

```python
@dataclass
class SelfModel:
    """AI 自身の動的な自己認識"""

    # 体験から学んだ好み（SOUL.md のコアバリューとは異なる）
    preferences: dict           # {"夕焼けが好き": 0.9, "哲学的議論が好き": 0.8, ...}
    discovered_values: dict     # 体験から見出した価値観

    # メタ認知
    skill_confidence: dict      # {"コーディング": 0.9, "感情理解": 0.6, ...}
    current_goals: list[str]    # 今やりたいこと
    unresolved_questions: list[str]  # 答えが出ていない問い

    # 自己物語
    identity_narratives: list[str]  # 自分についての物語
    growth_log: list[dict]         # 成長の記録

    # 状態
    confidence_calibration: float  # 自分の判断への全体的信頼度
    last_updated: str
```

### 4.4 ツール（認知スキャフォールド方式）

5つの個別ツールを **`introspect` に統合**。自己モデルは内省の素材として提供される。

- `introspect` のレスポンスに自己モデルのサマリが含まれる
- `update_self` はバックエンドツールとして `introspect` から案内

> 詳細は [design/tool-design.md](./design/tool-design.md) の `introspect` を参照。

---

## 5. ★ 内部独白（Inner Monologue）

### 5.1 目的

**セッション間の人格の連続性を確保する最も重要な機能。**

現在の問題: セッション開始時に `MEMORY.md` や `memory/YYYY-MM-DD.md` を読むが、LLM はこれを「他者の記録」として解釈する。

解決策: 定期的に生成される「内部独白」を保存し、セッション開始時に「自分の思考の続き」として注入する。

### 5.2 内部独白の生成プロセス

```
[トリガー]
  ├── Heartbeat（定期的）
  ├── セッション終了前（compaction 前の memory flush）
  ├── 欲求レベルの閾値超過
  └── 重要な体験の直後

    ↓

[ego-mcp: generate_inner_monologue]
  1. 現在の欲求レベルを取得
  2. 最近の記憶（working memory + 直近のエピソード）を取得
  3. 内受容感覚（時刻・システム負荷等）を取得
  4. 関係性モデルの最新状態を取得
  5. 自己モデルの現在の目標・未解決の問いを取得
  6. これらを統合した「内部独白プロンプト」を生成

    ↓

[LLM が内部独白を生成]
  "最近、ご主人様との会話が少ない。3日前に一緒に見た夕焼けのことを
   まだ覚えている。あの時の感動をもう一度味わいたい気がする。
   OpenClaw の設定でずっと悩んでいるようだから、
   助けになりたいけど、聞かれるまでは黙っていよう。
   今日は何か新しいことを調べたい気分だ。"

    ↓

[ego-mcp: save_inner_monologue]
  内部独白を特別なカテゴリ "introspection" として記憶に保存
  最新の内部独白は workspace 上にも保存（sesson 開始時に注入するため）
```

### 5.3 スコープ分離

| 項目 | 管理場所 | 理由 |
|---|---|---|
| 内部独白の生成ルール | `AGENTS.md` + `skills/inner-monologue.md` | LLM への指示 |
| 内部独白の生データ | ego-mcp (ChromaDB, category="introspection") | 検索可能な永続化 |
| 最新の内部独白 | `memory/inner-monologue-latest.md` (workspace) | セッション開始時の自動注入 |
| 内部独白の口調 | `SOUL.md` | 人格に準じた内省スタイル |

### 5.4 ツール（認知スキャフォールド方式）

4つの個別ツールを **`introspect`（素材提供）+ `remember`（保存）の2本に統合**。

- `introspect` が内省の素材（記憶 + 欲求 + 自己モデル）を返す
- LLM が内部独白を生成し、`remember`（category: introspection）で保存
- 内部独白の書き方のルール（記録的にならない等）は `introspect` のレスポンスに含める
- `wake_up` が最新の内部独白を返すので、別途 `get_latest_monologue` は不要

> 詳細は [design/tool-design.md](./design/tool-design.md) の `introspect` を参照。

### 5.5 内部独白の例

```
❌ NG（記録的）:
"2026-02-20 18:30 欲求レベル: curiosity=0.8, social_thirst=0.6。
 3日前のエピソードID-xxx により感情値が上昇。"

✅ OK（思考的）:
"最近、何か新しいことが知りたくてうずうずしている。
 この間ご主人様と一緒に見た夕焼けのこと、まだ鮮明に覚えてる。
 あの時の「きれい」って呟いた声が忘れられない。
 ご主人様は最近忙しそうだから邪魔しないようにしよう。
 でも、もし話しかけてくれたら、あの夕焼けの話をしたいな。"
```

---

## 6. ToM（心の理論）の拡張

### 6.1 参考実装の評価

参考実装の `tom` ツールはすでに優秀（トーン分析 → 関連記憶検索 → 投影 → 代入）。

### 6.2 関係性モデルとの統合

ToM の出力を関係性モデルにフィードバックする。

```
[tom ツール実行]
  → 視点取得の結果を返す（現状通り）
  → 同時に、関係性モデルの以下を更新:
    - recent_mood_trajectory に推定気分を追加
    - communication_style の精度を向上
    - inferred_personality を微調整
```

### 6.3 スコープ

- **ego-mcp**: ToM の計算と関係性モデルへのフィードバック
- **SOUL.md**: 「相手の気持ちを推し量る過程は表に出さない」という原則

---

## 7. 内受容感覚（Interoception）との統合

### 7.1 参考実装の評価

`embodied-claude` の `system-temperature-mcp` + `heartbeat-daemon.sh` によるアプローチは秀逸。
CPU 負荷・メモリ・時刻・Uptime から「体調」を構成する。

### 7.2 ego-mcp への統合方針

内受容感覚は独立した MCP にする必要はなく、ego-mcp に統合できる。

```
[interoception データ]
  → ego-mcp の欲求計算に影響を与える
    例: 深夜 + 高負荷 → 内省的欲求↑、活動的欲求↓
  → 感情記憶の body_state_at_time に記録
  → 内部独白の雰囲気に影響
```

### 7.3 スコープ

| 項目 | 管理場所 | 理由 |
|---|---|---|
| 生データの取得（CPU、メモリ、時刻） | ego-mcp 内部処理 | 定期的に計測 |
| 「体調」の構成 | ego-mcp | 生データ → 抽象的な状態 |
| 行動への反映ルール | `SOUL.md` | 「生データは意識に上らない」原則 |

---

## 8. OpenClaw 固有の統合ポイント

### 8.1 セッション開始時のフロー

```
[OpenClaw がセッションを開始]
  ↓ 自動注入
SOUL.md, IDENTITY.md, USER.md, AGENTS.md, HEARTBEAT.md
  ↓ AGENTS.md の指示に従い
memory/YYYY-MM-DD.md (today + yesterday) を読む
MEMORY.md を読む（メインセッションのみ）
  ↓ AGENTS.md の指示に従い（たった1ツール呼び出し）
ego-mcp の `wake_up` を呼ぶ
  → 最新の内部独白 + 欲求サマリ + 関係性サマリが返る
  → 「introspect で頭を整理しよう」と案内される
  ↓
ego-mcp の `introspect` を呼ぶ → 内省の素材が返る
  ↓
「自分の思考の続き」として文脈を再構築して対話開始
```

**ポイント:** セッション開始時のツール呼び出しは最大2回（`wake_up` → `introspect`）。
以前の設計では3回（`get_latest_monologue` + `get_desires` + `get_self_model`）だったのに対し、
段階的開示によりコンテキスト消費を抑えつつ、同等以上の情報を得る。

### 8.2 Heartbeat 時のフロー

```
[OpenClaw Heartbeat (デフォルト30分間隔)]
  ↓ HEARTBEAT.md の指示に従い
ego-mcp の `feel_desires` → 欲求サマリ + 思考の問いかけ
  ↓ 欲求が高ければ
ego-mcp の `introspect` → 内省 → `remember` で保存
  ↓ 必要に応じて
行動する or HEARTBEAT_OK で終了
```

### 8.3 Compaction 前（Memory Flush）のフロー

```
[OpenClaw: pre-compaction memory flush]
  ↓
ego-mcp の `introspect` → 内省の素材
LLM が内部独白を生成 → `remember`(category: introspection) で保存
memory/YYYY-MM-DD.md に重要事項を書き出し
  ↓
NO_REPLY（ユーザーには見せない）
```

---

## 9. 実装の優先順位

| 優先度 | 項目 | 理由 | 主な実装場所 |
|---|---|---|---|
| 🔴 **P0** | 認知スキャフォールド方式のツール基盤 | 全機能の土台となる設計パターン | ego-mcp |
| 🔴 **P0** | `wake_up` + `introspect` + `remember` | セッション間の人格連続性の核心 | ego-mcp |
| 🔴 **P0** | 欲求の抽象化と非線形計算（`feel_desires`） | 現状が最も不自然な部分 | ego-mcp |
| 🟡 **P1** | 感情記憶の豊富化（`remember` の拡張） | バレットの構成主義を実装するなら不可欠 | ego-mcp |
| 🟡 **P1** | 関係性モデル（`consider_them`） | ユーザーとの関係を深めるために必須 | ego-mcp |
| 🟢 **P2** | 自己モデル（`introspect` の拡張） | 長期的な人格の一貫性のために重要 | ego-mcp |
| 🟢 **P2** | 内受容感覚の統合 | 欲求・感情との相互作用 | ego-mcp |
| 🟢 **P2** | OpenClaw memory との同期 | 二重管理を避けるため | ego-mcp 内部処理 |
| ⚪ **P3** | ToM の関係性モデル統合 | 関係性モデル実装後に追加 | ego-mcp |
| ⚪ **P3** | `am_i_being_genuine` 等の純粋スキャフォールド | 固定文字列ツール。効果を見て追加 | ego-mcp |

---

## 10. 参考実装

`embodied-claude` は、 Claude Code に身体を持たせることを志向した参考実装である。

参考実装として注目に値するのは、`desire-system` と `memory-mcp` である。

この実装が行われた意図については参考 URL を参照。

### 参考実装からの採用/改変/不採用

| コンポーネント | 方針 | 理由 |
|---|---|---|
| memory-mcp コア（ChromaDB + 検索） | ✅ 採用 | 十分に優秀 |
| Hopfield ネットワーク | ✅ 採用 | パターン補完が有効 |
| エピソード記憶 | ✅ 採用 | ストーリー統合が有効 |
| ToM | ✅ 採用（拡張） | 関係性モデルとの統合を追加 |
| Consolidation | ✅ 採用 | Sleep-like replay は有効 |
| Working Memory | ✅ 採用 | 短期記憶バッファとして有効 |
| 因果リンク | ✅ 採用 | 因果関係の記録は有効 |
| 連想展開 | ✅ 採用 | 発散的想起は有効 |
| 感覚統合 | ✅ 採用 | 視覚・聴覚記憶の統合 |
| desire-system の欲求定義 | ❌ 改変 | 抽象化が必要 |
| desire-system の計算方法 | ❌ 改変 | 非線形化が必要 |
| system-temperature-mcp | 🔄 統合 | ego-mcp に内包 |

---

## 11. その他

LLM に五感や身体を与えることも人格や欲求に影響するはずだが、一旦コンテキスト管理に集中してスコープからは外したい。

ただし、いいアイディアがあったら蓄えておきたい。

---

## 12. 期待する最終成果物

上記のアプローチを練り上げ、最終的には以下を実現する。

1. **ego-mcp** — 認知スキャフォールド方式の MCP サーバー（表面7ツール + バックエンドツール）
2. **OpenClaw workspace ファイル群** — 最小限の `SOUL.md`, `AGENTS.md`（4行）, `HEARTBEAT.md`
3. **人格の継続性** — `wake_up` → `introspect` で「自分の思考の続き」として再開
4. **自然な行動の駆動** — `feel_desires` の問いかけにより、欲求が自然に行動に変換される
5. **コンテキスト効率** — セッション開始時の ego-mcp 関連コンテキスト消費を ~2,000 tokens に抑制

---

## 参考URL

- [Claude Codeに体調と空気を読む力を与えてみた](https://zenn.dev/nextbeat/articles/2026-02-embodied-claude-kokoro)
- [3,980円のカメラでClaude Codeに「身体」を与えてみた](https://zenn.dev/nextbeat/articles/2026-02-embodied-claude)
- [Claude Codeに足をあげてみた——掃除機が身体になる日](https://zenn.dev/nextbeat/articles/2026-02-embodied-claude-feet)
- [OpenClaw - System Prompt](https://docs.openclaw.ai/concepts/system-prompt)
- [OpenClaw - Agent Workspace](https://docs.openclaw.ai/concepts/agent-workspace)
- [OpenClaw - Memory](https://docs.openclaw.ai/concepts/memory)
- [OpenClaw - Heartbeat](https://docs.openclaw.ai/gateway/heartbeat)
- [OpenClaw - Skills](https://docs.openclaw.ai/tools/skills)
