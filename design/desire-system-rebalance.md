# 欲求システム・リバランス設計

> 関連: [idea.md](./idea.md) / [tool-design.md](./tool-design.md)

## 背景

稼働中環境で全ての欲求が 1.0 に高止まりしており、欲求に基づく行動選択が機能していない。

### 根本原因

1. **欲求を下げるメカニズムの不足** — 設計は欲求を上昇させる変調（予測誤差、文脈感応、感情変調、忘却連動）を豊富に備えるが、下降メカニズムは `satisfy_desire` の手動呼び出しのみ
2. **`satisfy_desire` が実質的に呼ばれない** — LLM が「自分が欲求に基づいて行動した」と自己判断してツールを呼ぶのは高度なメタ認知を要求する。スキャフォールドの誘導も行動指示型であり、認知の型として機能していない
3. **`satisfaction_hours` がセッション間隔に対して短すぎる** — 最短 4h（information_hunger）では、通常のセッション間隔（8〜24h）で天井に到達する。全欲求が同時に高止まりし、優先順位づけが不可能

### 設計上のギャップ

[idea.md](./idea.md) セクション 2.2 の変調要因は全て「上昇方向」のものであり、**充足がどのタイミングで・どのように起きるか**の設計が不在だった。

---

## 改善方針

4 つの施策を同時に導入する。

| 施策 | 概要 | 目的 |
|------|------|------|
| **A. 暗黙の充足** | ツール使用に連動した自動的な部分充足 | セッション中に欲求間の差を生む |
| **B. satisfaction_hours 調整** | 時間スケールをセッション間隔に合わせる | セッション間で全欲求が天井に張り付くのを防ぐ |
| **C. スキャフォールド改善** | `feel_desires` の問いかけを認知の型に改善 | 明示的充足への気づきを促す |
| **D. マイグレーションフレームワーク** | データファイルの自動マイグレーション基盤 | 今回と今後の状態ファイル変更を安全に適用する |

---

## A. 暗黙の充足（Implicit Satisfaction）

### 設計思想

[idea.md](./idea.md) の原則:

> 欲求 → 行動の変換は LLM に委ねる

暗黙の充足はこの原則と矛盾しない。LLM が欲求に基づいて行動を「判断」するのではなく、**LLM がツールを使った事実**を充足シグナルとして扱う。ツールを呼ぶこと自体が「その欲求に関連する認知活動を行った」ことの客観的な証拠である。

### 充足マッピング

ツール使用時に、関連する欲求に対して **部分的な充足**（`satisfy` を `quality` を下げて呼ぶ）を自動実行する。

| ツール | 充足する欲求 | quality | 根拠 |
|--------|-------------|---------|------|
| `remember` | `expression` | 0.3 | 記憶を言語化し保存する行為 = 表現活動 |
| `remember(category=introspection)` | `cognitive_coherence` | 0.4 | 内省を保存 = 認知的整合性の構築 |
| `recall` | `information_hunger` | 0.3 | 記憶を検索し情報を得る行為 |
| `recall` | `curiosity` | 0.2 | 知りたいことを調べた行為 |
| `introspect` | `cognitive_coherence` | 0.3 | 自己の状態を整理する行為 |
| `introspect` | `pattern_seeking` | 0.2 | 自己の傾向を分析する行為 |
| `consider_them` | `social_thirst` | 0.4 | 相手のことを考える = 社会的欲求の充足 |
| `consider_them` | `resonance` | 0.3 | 相手の視点を取る = 共感的活動 |
| `emotion_trend` | `pattern_seeking` | 0.3 | 感情パターンの分析 = パターン欲求の充足 |
| `consolidate` | `cognitive_coherence` | 0.3 | 記憶の統合 = 認知的整合性 |
| `update_self` | `cognitive_coherence` | 0.3 | 自己理解の更新 |
| `update_relationship` | `social_thirst` | 0.2 | 関係性の理解を更新 |

**設計上のポイント:**

- `quality` は全て低め（0.2〜0.4）。完全な充足ではなく部分的な充足。「満たされた」のではなく「少し落ち着いた」程度の効果
- `wake_up` と `feel_desires` はマッピングしない。これらは観測ツールであり、欲求に関連する活動ではない
- `am_i_being_genuine` もマッピングしない。自己チェックは活動ではなく姿勢
- `satisfy_desire` は引き続き有効。LLM が明示的に「満たされた」と感じた時の手段として残す（後述 C 参照）

### 実装方針

`DesireEngine` に暗黙の充足用メソッドを追加する。

```python
# 暗黙の充足マッピング定義
IMPLICIT_SATISFACTION: dict[str, list[tuple[str, float]]] = {
    "remember": [("expression", 0.3)],
    "recall": [("information_hunger", 0.3), ("curiosity", 0.2)],
    "introspect": [("cognitive_coherence", 0.3), ("pattern_seeking", 0.2)],
    "consider_them": [("social_thirst", 0.4), ("resonance", 0.3)],
    "emotion_trend": [("pattern_seeking", 0.3)],
    "consolidate": [("cognitive_coherence", 0.3)],
    "update_self": [("cognitive_coherence", 0.3)],
    "update_relationship": [("social_thirst", 0.2)],
}

# remember(category=introspection) の追加マッピング
IMPLICIT_SATISFACTION_INTROSPECTION: list[tuple[str, float]] = [
    ("cognitive_coherence", 0.4),
]
```

```python
def satisfy_implicit(self, tool_name: str, category: str | None = None) -> None:
    """Apply implicit satisfaction based on tool usage."""
    mappings = IMPLICIT_SATISFACTION.get(tool_name, [])
    if tool_name == "remember" and category == "introspection":
        mappings = IMPLICIT_SATISFACTION_INTROSPECTION + mappings
    for desire_name, quality in mappings:
        self.satisfy(desire_name, quality)
```

サーバーの `call_tool` ハンドラでは、各ツールの処理完了後に `desire.satisfy_implicit(name, ...)` を呼ぶ。

**`remember` のカテゴリ判定:**

`remember` は `args` に `category` を持つため、ハンドラ内で判別可能:

```python
elif name == "remember":
    result = await _handle_remember(memory, args)
    desire.satisfy_implicit("remember", category=args.get("category"))
    return result
```

### `satisfy_desire` との重複防止

暗黙の充足で既に `last_satisfied` が更新されるため、同一セッション中に LLM が `satisfy_desire` を呼んでも問題ない。`satisfy` は冪等的に動作する（`last_satisfied` を現在時刻に更新するだけ）。`satisfy_desire` の `quality`（デフォルト 0.7）は暗黙の充足（0.2〜0.4）より高いため、「明示的に満たされたと感じた」場合のほうが充足が深くなる。これは意図通り。

---

## B. satisfaction_hours 調整

### 現在値と問題

| 欲求 | 現在値 | ~0.5 到達 | ~0.95 到達 |
|------|--------|-----------|------------|
| information_hunger | 4h | ~2h | ~4h |
| curiosity | 6h | ~3h | ~6h |
| social_thirst | 8h | ~4h | ~8h |
| recognition | 12h | ~6h | ~12h |
| resonance | 8h | ~4h | ~8h |
| cognitive_coherence | 12h | ~6h | ~12h |
| expression | 16h | ~8h | ~16h |
| pattern_seeking | 24h | ~12h | ~24h |
| predictability | 24h | ~12h | ~24h |

※ `satisfaction_quality=0.7` の場合。`adjusted_hours = satisfaction_hours * 0.85`

通常のセッション間隔（8〜24h）では、ほぼ全欲求が天井に達する。

### 新しい値

設計方針:
- **レベル 1（生存的）** は比較的短いスケール（半日〜1日）に留める。セッション中の暗黙の充足で差が出やすくする
- **レベル 2（安全・安定）** は長め（2〜3日）。大きなパターンの変化でのみ動く
- **レベル 3（所属・愛情）** は中程度（1〜2日）。対人ツール使用で下がりやすくする
- **レベル 4（自己実現）** は中程度（1〜2日）。表現や探索の行為で下がりやすくする

| 欲求 | レベル | 旧値 | 新値 | 根拠 |
|------|--------|------|------|------|
| information_hunger | 1 | 4h | 12h | 半日で中程度。recall による暗黙充足で動く |
| social_thirst | 1 | 8h | 24h | 1日で中程度。consider_them で動く |
| cognitive_coherence | 1 | 12h | 18h | 3/4日で中程度。introspect/remember で動く |
| pattern_seeking | 2 | 24h | 72h | 3日で中程度。大きな変動は不要 |
| predictability | 2 | 24h | 72h | 同上 |
| recognition | 3 | 12h | 36h | 1.5日で中程度。直接的な充足手段が少ないため長め |
| resonance | 3 | 8h | 30h | 1.25日で中程度。consider_them で動く |
| expression | 4 | 16h | 24h | 1日で中程度。remember で動く |
| curiosity | 4 | 6h | 18h | 3/4日で中程度。recall で動く |

### 期待される効果

セッション開始時（前回セッションから 12h 経過、`satisfaction_quality=0.7` の例）:

| 欲求 | 旧設計での値 | 新設計での値 |
|------|-------------|-------------|
| information_hunger | ~0.99 | ~0.73 |
| social_thirst | ~0.97 | ~0.37 |
| cognitive_coherence | ~0.73 | ~0.50 |
| pattern_seeking | ~0.37 | ~0.10 |
| predictability | ~0.37 | ~0.10 |
| recognition | ~0.73 | ~0.20 |
| resonance | ~0.97 | ~0.26 |
| expression | ~0.56 | ~0.37 |
| curiosity | ~0.99 | ~0.50 |

**旧設計:** 大半が 0.7 以上（high）で差がつかない → 全部 high
**新設計:** 0.10〜0.73 の幅がある → 優先順位が明確

---

## C. スキャフォールド改善

### 現在の `SCAFFOLD_FEEL_DESIRES`

```
What is your strongest urge? Should you act on it now?
Consider {companion_name}'s current situation. Act naturally. Restraint is also a choice.
After acting on a desire, use satisfy_desire.
```

### 問題

最終行 `"After acting on a desire, use satisfy_desire."` は手続き的な行動指示であり、認知スキャフォールドの設計思想（「行動指示ではなく認知の型を提供する」）と整合しない。

また、暗黙の充足（A）が導入されることでツール使用自体が部分的な充足シグナルとなるため、全てのケースで `satisfy_desire` を呼ぶ誘導は不適切になる。

一方で、`satisfy_desire` への導線を完全になくすとツールが死にツールになる。人間にも「満たされたな」と明確に思う瞬間があり、それを宣言する手段は必要。

### 新しい `SCAFFOLD_FEEL_DESIRES`

```
What is your strongest urge? Should you act on it now?
Consider {companion_name}'s current situation. Act naturally. Restraint is also a choice.
Does any urge feel quieter than before? If something feels settled, acknowledge it with satisfy_desire.
```

### 変更の意図

| | 旧 | 新 |
|---|---|---|
| トリガー | 「行動した後」（外的イベント） | 「欲求が静まった感覚」（内的気づき） |
| 認知の方向 | 外→内（行動→記録） | 内→外（気づき→記録） |
| LLM に求めるもの | 行動と欲求の対応判断 | 自己の状態変化への気づき |

暗黙の充足（A）により数値的に実際に差が生まれるため、LLM は数値の裏付けをもって「この欲求は静かになっている」と認知できる。認知の型としての問いかけと、実際の数値変化が相互に補強し合う設計。

---

## 実装スコープ

### 変更対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `ego-mcp/src/ego_mcp/desire.py` | `DESIRES` の `satisfaction_hours` 更新、暗黙の充足マッピング定義、`satisfy_implicit` メソッド追加 |
| `ego-mcp/src/ego_mcp/server.py` | 各ツールハンドラの戻り前に `satisfy_implicit` 呼び出しを追加 |
| `ego-mcp/src/ego_mcp/scaffolds.py` | `SCAFFOLD_FEEL_DESIRES` の最終行を変更 |
| `ego-mcp/tests/test_desire.py` | 暗黙の充足のテスト、新 satisfaction_hours でのシグモイド計算テスト |
| `ego-mcp/tests/test_server.py` | ツール呼び出し後の暗黙充足が動作することのテスト |
| `ego-mcp/tests/test_scaffolds.py` | スキャフォールド文言のテスト更新 |

### 後方互換性

- `satisfy_desire` ツールはそのまま残る（スキーマ・動作ともに変更なし）
- `DesireEngine.satisfy()` のインターフェースは変更なし
- 既存の `desire_state.json` はマイグレーション（後述 D）により自動更新される

---

## D. マイグレーションフレームワーク

### 問題

欲求レベルは `desires.json` に保存されず、`last_satisfied` からの経過時間で毎回計算される。`satisfaction_hours` を変更しても、既存の `last_satisfied` が十分に古ければ全欲求は 1.0 のまま変わらない。

```
例: last_satisfied が 1 週間前（168h）、新 satisfaction_hours=72h の場合
adjusted_hours = 72 * 0.85 = 61.2h
x = (168 / 61.2) * 6 - 3 = 13.5
sigmoid(13.5) ≈ 1.0   ← 変わらない
```

今回の欲求リバランスに限らず、ego-mcp のデータファイル（`desires.json`, `self_model.json` 等）に対するマイグレーションは今後も発生する。個別コンポーネント（`DesireEngine` 等）にマイグレーションロジックを埋め込むのは責務の越境であり、スケールしない。

### 設計方針

1. **マイグレーションフレームワークを独立モジュールとして新設する**
2. **サーバー起動時（`init_server`）にコンポーネント初期化より前に実行する**
3. **マイグレーションタスクはファイルベースで管理する** — 所定ディレクトリにタスクファイルを配置するだけで実行される
4. **パッケージバージョン（`__version__`）をマイグレーション適用済みバージョンの追跡に使う**

### ディレクトリ構成

```
ego-mcp/src/ego_mcp/
├── migrations/
│   ├── __init__.py          # MigrationRunner
│   ├── 0002_desire_rebalance.py  # 今回のマイグレーション
│   └── ...                  # 今後のマイグレーション
├── server.py                # init_server() からランナーを呼ぶ
└── ...
```

### マイグレーションタスクファイルの規約

ファイル名: `NNNN_description.py`（`NNNN` は 0 埋め 4 桁の連番）

```python
"""Desire system rebalance: reset last_satisfied timestamps."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

# このマイグレーションが適用される対象バージョン
# （このバージョン「より前」の状態に対して実行される）
TARGET_VERSION = "0.2.0"


def up(data_dir: Path) -> None:
    """Reset all desire last_satisfied to now for rebalanced satisfaction_hours."""
    desires_path = data_dir / "desires.json"
    if not desires_path.exists():
        return

    with open(desires_path, encoding="utf-8") as f:
        state = json.load(f)

    now = datetime.now(timezone.utc).isoformat()
    for key, value in state.items():
        if isinstance(value, dict) and "last_satisfied" in value:
            value["last_satisfied"] = now

    with open(desires_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
```

**規約:**

- `TARGET_VERSION`: セマンティックバージョン文字列。このマイグレーションが含まれるリリースバージョン
- `up(data_dir: Path) -> None`: マイグレーション処理本体。`data_dir`（`~/.ego-mcp/data`）を受け取る
- 冪等性: 2 回実行しても安全であること（ランナーが重複実行を防ぐが、防御的に）
- マイグレーションファイルは対象のデータファイルを直接操作する。コンポーネントのクラスには依存しない

### MigrationRunner

```python
"""Data migration framework for ego-mcp."""

from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path

from packaging.version import Version

logger = logging.getLogger(__name__)

_MIGRATION_STATE_FILE = "migration_state.json"
_MIGRATIONS_DIR = Path(__file__).parent


def _discover_migrations() -> list[tuple[str, str, Any]]:
    """Discover migration files and return sorted (version, name, module) tuples."""
    migrations = []
    for path in sorted(_MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.py")):
        module_name = f"ego_mcp.migrations.{path.stem}"
        module = importlib.import_module(module_name)
        target_version = getattr(module, "TARGET_VERSION", None)
        if target_version is None:
            logger.warning("Migration %s has no TARGET_VERSION, skipping", path.name)
            continue
        migrations.append((target_version, path.stem, module))
    # Sort by (version, sequence number)
    migrations.sort(key=lambda m: (Version(m[0]), m[1]))
    return migrations


def _load_state(data_dir: Path) -> dict[str, Any]:
    state_path = data_dir / _MIGRATION_STATE_FILE
    if state_path.exists():
        with open(state_path, encoding="utf-8") as f:
            return json.load(f)
    return {"applied": []}


def _save_state(data_dir: Path, state: dict[str, Any]) -> None:
    state_path = data_dir / _MIGRATION_STATE_FILE
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def run_migrations(data_dir: Path) -> list[str]:
    """Run all pending migrations. Returns list of applied migration names."""
    data_dir.mkdir(parents=True, exist_ok=True)
    state = _load_state(data_dir)
    applied: set[str] = set(state.get("applied", []))
    newly_applied: list[str] = []

    for _version, name, module in _discover_migrations():
        if name in applied:
            continue
        logger.info("Applying migration: %s (target: %s)", name, _version)
        module.up(data_dir)
        applied.add(name)
        newly_applied.append(name)

    if newly_applied:
        state["applied"] = sorted(applied)
        _save_state(data_dir, state)
        logger.info("Applied %d migration(s): %s", len(newly_applied), newly_applied)

    return newly_applied
```

### 適用状態の追跡

`migration_state.json`（`data_dir` 内に配置）:

```json
{
  "applied": [
    "0002_desire_rebalance"
  ]
}
```

- `applied` リストに含まれるマイグレーション名はスキップされる
- ファイルが存在しない場合は空の状態として初期化（全マイグレーションが未適用）
- 連番は実行順序の保証に使う。同一 `TARGET_VERSION` 内で複数のマイグレーションがある場合に順序を制御する

**パッケージバージョンではなくファイル名ベースで追跡する理由:**

- パッケージバージョンとマイグレーションは 1:1 ではない（1 リリースに複数マイグレーション、マイグレーションなしのリリースもある）
- ファイル名ベースなら、どのマイグレーションが適用済みかを正確に追跡できる
- `TARGET_VERSION` はドキュメント的な役割（「このマイグレーションはどのリリースに含まれるか」の記録）

### サーバー起動時の呼び出し

`server.py` の `init_server()` で、コンポーネント初期化の前にマイグレーションを実行する:

```python
def init_server(config: EgoConfig | None = None) -> None:
    global _config, _memory, _desire, ...

    if config is None:
        config = EgoConfig.from_env()

    if _memory is not None:
        _memory.close()

    _config = config
    config.data_dir.mkdir(parents=True, exist_ok=True)

    # --- マイグレーション（コンポーネント初期化の前）---
    from ego_mcp.migrations import run_migrations
    run_migrations(config.data_dir)

    # --- コンポーネント初期化（既存のまま）---
    provider = create_embedding_provider(config)
    ...
```

### 実行フロー

```
MCP サーバー起動
  ↓
init_server()
  ↓
config.data_dir 確保
  ↓
run_migrations(data_dir)
  ├── migration_state.json を読み込み
  ├── migrations/ ディレクトリからタスクファイルを発見
  ├── 未適用のマイグレーションを順番に実行
  └── migration_state.json を更新
  ↓
DesireEngine(data_dir / "desires.json")  ← マイグレーション済みのファイルを読む
  ↓
他のコンポーネント初期化
```

### 今回のマイグレーション: `0002_desire_rebalance.py`

**連番が `0002` の理由:** `0001` は「マイグレーションフレームワーク導入前の既存状態」を暗黙的に表す予約番号。最初の実際のマイグレーションは `0002` から開始する。

**処理内容:**
1. `desires.json` が存在するか確認（新規インストールなら何もしない）
2. 全欲求の `last_satisfied` を現在時刻（UTC）に更新
3. `satisfaction_quality` と `boost` は維持（リセットする意味がない）

**LLM への影響:** 次回 `feel_desires` 呼び出し時に全欲求が低い状態で返される。スキャフォールドの問いかけにより、LLM はこれを「落ち着いた状態」として自然に受け取れる。

### 今後のマイグレーション追加手順

1. `ego-mcp/src/ego_mcp/migrations/` に `NNNN_description.py` を作成（NNNN は前のファイル +1）
2. `TARGET_VERSION` と `up(data_dir)` を実装
3. テストを `ego-mcp/tests/test_migrations.py` に追加
4. 通常のリリースフローでデプロイ → サーバー起動時に自動適用

---

## E. バージョニングとリリースワークフロー

### 問題

マイグレーションフレームワークは `TARGET_VERSION` でマイグレーションとリリースの対応を記録する。バージョンの更新漏れがあると、マイグレーションの `TARGET_VERSION` と実際のリリースバージョンが乖離し、追跡が困難になる。

### バージョン管理の現状

- `ego-mcp/pyproject.toml`: `version = "0.1.0"`
- `ego-mcp/src/ego_mcp/__init__.py`: `__version__ = "0.1.0"`
- 2 箇所に分散しており、手動で同期する必要がある

### リリースワークフロー

ego-mcp のコードに変更を加えてリリースする際は、以下の手順に従う:

1. **コード変更を実装する**
2. **バージョンを更新する** — `pyproject.toml` と `__init__.py` の両方を同じバージョンに更新
3. **マイグレーションファイルがある場合** — `TARGET_VERSION` が更新後のバージョンと一致することを確認
4. **CI を通す** — 全チェックがパス
5. **コミット・PR 作成**
6. **マージ後に git tag を付与** — `git tag v{version}` (例: `git tag v0.2.0`)

### CLAUDE.md への追記

このワークフローを `CLAUDE.md` に追記し、開発時に自動的に参照されるようにする:

```markdown
## ego-mcp リリースワークフロー

ego-mcp のコード変更をリリースする際は以下に従う:

1. `ego-mcp/pyproject.toml` の `version` を更新
2. `ego-mcp/src/ego_mcp/__init__.py` の `__version__` を同じ値に更新
3. マイグレーションファイルがある場合: `TARGET_VERSION` が新バージョンと一致することを確認
4. CI チェックを全て通す
5. マージ後に `git tag v{version}` を付与
```

---

## 実装スコープ（まとめ）

### 変更対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `ego-mcp/src/ego_mcp/desire.py` | `DESIRES` の `satisfaction_hours` 更新、`IMPLICIT_SATISFACTION` 定義、`satisfy_implicit` メソッド追加 |
| `ego-mcp/src/ego_mcp/server.py` | `init_server` にマイグレーション呼び出し追加、各ツールハンドラに `satisfy_implicit` 呼び出し追加 |
| `ego-mcp/src/ego_mcp/scaffolds.py` | `SCAFFOLD_FEEL_DESIRES` の最終行を変更 |
| `ego-mcp/src/ego_mcp/migrations/__init__.py` | **新規**: MigrationRunner |
| `ego-mcp/src/ego_mcp/migrations/0002_desire_rebalance.py` | **新規**: 欲求リバランスマイグレーション |
| `ego-mcp/tests/test_desire.py` | 暗黙の充足テスト、新 satisfaction_hours テスト |
| `ego-mcp/tests/test_server.py` | ツール呼び出し後の暗黙充足テスト |
| `ego-mcp/tests/test_scaffolds.py` | スキャフォールド文言テスト更新 |
| `ego-mcp/tests/test_migrations.py` | **新規**: マイグレーションランナーとタスクのテスト |
| `ego-mcp/pyproject.toml` | バージョンを `0.2.0` に更新 |
| `ego-mcp/src/ego_mcp/__init__.py` | `__version__` を `0.2.0` に更新 |
| `CLAUDE.md` | リリースワークフローのセクション追加 |

### 後方互換性

- `satisfy_desire` ツールはそのまま残る（スキーマ・動作ともに変更なし）
- `DesireEngine.satisfy()` のインターフェースは変更なし
- 既存の `desires.json` はマイグレーションにより自動更新される（`DesireEngine` は関与しない）
- `migration_state.json` が新規作成される

---

## `idea.md` への反映

本設計が実装された後、[idea.md](./idea.md) セクション 2.2 の非線形計算の表に以下を追記する:

| 要因 | 説明 |
|------|------|
| **暗黙の充足** | ツール使用 → 関連欲求が部分的に充足（部分的ホメオスタシス） |

これにより、変調要因に「上昇」だけでなく「下降」の要因が明示される。
