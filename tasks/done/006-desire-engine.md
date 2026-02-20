# 006: 欲求エンジン（DesireEngine）

## 目的
抽象的欲求のレベル計算・充足・ブーストを管理する。

## 前提
- 004（types）完了済み

## 参照
- `idea.md` §2.2（欲求定義）、§2.3（非線形計算）
- 参考実装: `embodied-claude/desire-system/desire_updater.py`（計算ロジックの参考。ただし抽象化する）

## 仕様

`src/ego_mcp/desire.py` に `DesireEngine` クラス:

```python
DESIRES = {
    "information_hunger":  {"satisfaction_hours": 4,  "level": 1},
    "social_thirst":       {"satisfaction_hours": 8,  "level": 1},
    "cognitive_coherence":  {"satisfaction_hours": 12, "level": 1},
    "pattern_seeking":     {"satisfaction_hours": 24, "level": 2},
    "predictability":      {"satisfaction_hours": 24, "level": 2},
    "recognition":         {"satisfaction_hours": 12, "level": 3},
    "resonance":           {"satisfaction_hours": 8,  "level": 3},
    "expression":          {"satisfaction_hours": 16, "level": 4},
    "curiosity":           {"satisfaction_hours": 6,  "level": 4},
}

class DesireEngine:
    def __init__(self, state_path: Path): ...     # JSON永続化
    def compute_levels(self) -> dict[str, float]: ...  # 全欲求レベルをシグモイド計算
    def satisfy(self, name: str, quality: float = 0.7): ...  # last_satisfied を now に
    def boost(self, name: str, amount: float): ...   # clamp to 1.0
    def format_summary(self) -> str: ...             # "curiosity[high] social_thirst[mid] ..."
    def save_state(self) / load_state(self): ...     # JSON read/write
```

**レベル計算（シグモイド）:**
```python
adjusted_hours = satisfaction_hours * (0.5 + 0.5 * satisfaction_quality)
x = (elapsed_hours / adjusted_hours) * 6 - 3
base_level = 1.0 / (1.0 + math.exp(-x))
```

**format_summary 出力:** 英語。`[high]`(>=0.7), `[mid]`(>=0.4), `[low]`(<0.4)。高い順にソート。

## テスト
- 8時間経過後の social_thirst が ~0.5
- satisfy 後に level 低下
- boost で level 増加（上限1.0）
- format_summary が英語の正しいフォーマット
- save/load で状態が永続化

## 完了確認
```bash
pytest tests/test_desire.py -v  # 全 pass
```
