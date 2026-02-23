# 701: satisfaction_hours の調整

## 目的
欲求のシグモイド計算に使う `satisfaction_hours` を調整し、セッション間隔（8〜24h）で全欲求が天井に張り付く問題を解消する。

## 前提
- 700（マイグレーションフレームワーク）が完了していること

## 参照
- `design/desire-system-rebalance.md` §B

## タスク

### T-701-1: `DESIRES` 定数の更新
対象ファイル: `src/ego_mcp/desire.py`

`DESIRES` の `satisfaction_hours` を以下に変更する:

| 欲求 | 旧値 | 新値 |
|------|------|------|
| information_hunger | 4 | 12 |
| social_thirst | 8 | 24 |
| cognitive_coherence | 12 | 18 |
| pattern_seeking | 24 | 72 |
| predictability | 24 | 72 |
| recognition | 12 | 36 |
| resonance | 8 | 30 |
| expression | 16 | 24 |
| curiosity | 6 | 18 |

`level`（マズロー階層）は変更しない。

### T-701-2: マイグレーションタスクファイルの作成
対象ファイル: `src/ego_mcp/migrations/0002_desire_rebalance.py`（新規）

`satisfaction_hours` の変更に合わせて、既存の `desires.json` の全欲求の `last_satisfied` を現在時刻（UTC）にリセットするマイグレーションを作成する。

```python
TARGET_VERSION = "0.2.0"

def up(data_dir: Path) -> None:
    # desires.json が存在しなければ何もしない（新規インストール）
    # 全欲求エントリの last_satisfied を datetime.now(timezone.utc).isoformat() に更新
    # satisfaction_quality と boost は既存値を維持
```

`desires.json` が存在しない場合（新規インストール）は何もせず return する。

### T-701-3: テストの更新
対象ファイル: `tests/test_desire.py`

- 既存のシグモイド計算テストを新しい `satisfaction_hours` に合わせて期待値を更新する
- マイグレーション `0002_desire_rebalance` のテスト:
  - 旧形式の `desires.json`（古い `last_satisfied`）に対して `up()` を実行すると、`last_satisfied` が現在時刻付近に更新されること
  - `desires.json` が存在しない場合に `up()` がエラーなく完了すること

## 完了確認
```bash
cd ego-mcp
GEMINI_API_KEY=test-key uv run pytest tests/test_desire.py tests/test_migrations.py -v
uv run mypy src/ego_mcp/desire.py src/ego_mcp/migrations
```
