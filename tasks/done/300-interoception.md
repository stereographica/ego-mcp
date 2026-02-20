# 300: 内受容感覚（Interoception）（Phase 3）

## 目的
時刻帯とシステム状態を欲求計算へ取り込み、`feel_desires` を状況適応型にする。

## 前提
- `DesireEngine.compute_levels()` が安定動作していること
- `feel_desires` が統合テスト済みであること

## 参照
- `design/tasks.md` の T-300

## タスク

### T-300-1: `src/ego_mcp/interoception.py` の実装
- [ ] `time_phase` 判定関数を実装
  - `early_morning`, `morning`, `afternoon`, `evening`, `night`, `late_night`
- [ ] `system_load` 判定関数を実装
  - `psutil` 利用可なら優先、不可時は `os.getloadavg()` フォールバック
  - `low`, `medium`, `high` へ離散化
- [ ] `get_body_state() -> dict[str, str]` を実装

### T-300-2: `feel_desires` への統合
- [ ] `time_phase` 補正を実装
  - `late_night`: `cognitive_coherence +0.1`, `social_thirst -0.1`
  - `morning`: `curiosity +0.05`
- [ ] `system_load == high` で全欲求を `0.9` 倍に抑制
- [ ] 出力サマリに補正後の値を反映

## テスト
- [ ] `tests/test_interoception.py` を作成
  - 時刻別 `time_phase` 判定
  - 負荷別 `system_load` 判定
- [ ] `tests/test_desire.py` or `tests/test_integration.py` に `feel_desires` 補正確認を追加

## 完了確認
```bash
cd ego-mcp
uv run pytest tests/test_interoception.py -v
uv run pytest tests/test_integration.py -k feel_desires -v
```

