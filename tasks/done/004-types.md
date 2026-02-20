# 004: 共通型定義（types.py）

## 目的
ego-mcp 全体で使う中核データ構造を定義する。

## 仕様

`src/ego_mcp/types.py`:

**Enums:**
- `Emotion(str, Enum)`: happy, sad, surprised, moved, excited, nostalgic, curious, neutral
- `Category(str, Enum)`: daily, philosophical, technical, memory, observation, feeling, conversation, **introspection, relationship, self_discovery, dream, lesson**
- `LinkType(str, Enum)`: similar, caused_by, leads_to, related

**Dataclasses:**

| クラス | 主なフィールド |
|---|---|
| `BodyState` | time_phase, system_load, uptime_hours |
| `EmotionalTrace` | primary(Emotion), secondary, intensity, valence, arousal, body_state |
| `MemoryLink` | target_id, link_type, note, confidence |
| `Memory` | id, content, timestamp, emotional_trace, importance(1-5), category, linked_ids, tags |
| `MemorySearchResult` | memory, distance, score |
| `DesireState` | name, level(0-1), last_satisfied(ISO), satisfaction_quality(0-1) |
| `RelationshipModel` | person_id, name, known_facts, communication_style, emotional_baseline, trust_level, shared_episode_ids, inferred_personality, first/last_interaction, total_interactions |
| `SelfModel` | preferences, discovered_values, skill_confidence, current_goals, unresolved_questions, identity_narratives, growth_log, confidence_calibration |

- `Memory.now_iso()` staticmethod で UTC ISO 8601 文字列を返す
- 全 mutable フィールドは `field(default_factory=...)` でインスタンス間共有を防ぐ

## テスト（`tests/test_types.py`）
- Enum 値の一致確認
- 各 dataclass のデフォルト構築
- mutable フィールドがインスタンス間で共有されていないこと

## 完了確認
```bash
pytest tests/test_types.py -v  # 全 pass
mypy src/ego_mcp/types.py      # Success
```
