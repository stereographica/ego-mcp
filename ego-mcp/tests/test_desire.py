"""Tests for DesireEngine."""

from __future__ import annotations

import importlib
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ego_mcp.desire import (
    DESIRES,
    DesireEngine,
    _calculate_sigmoid_level,
    generate_emergent_from_recent_memories,
)
from ego_mcp.desire_blend import blend_desires
from ego_mcp.desire_catalog import (
    DesireConfigurationError,
    default_desire_catalog,
    desire_catalog_settings_path,
    load_desire_catalog,
)
from ego_mcp.types import Emotion, EmotionalTrace, Memory, Notion


class TestSigmoidCalculation:
    """Test the non-linear sigmoid desire calculation."""

    def test_zero_elapsed(self) -> None:
        """Just satisfied → level near 0."""
        level = _calculate_sigmoid_level(0.0, 8.0, 0.5)
        assert level < 0.1

    def test_at_satisfaction_hours(self) -> None:
        """At satisfaction_hours with quality=1.0 → sigmoid(3) ≈ 0.95."""
        level = _calculate_sigmoid_level(8.0, 8.0, 1.0)
        # adjusted_hours = 8 * (0.5 + 0.5*1.0) = 8
        # x = (8/8)*6 - 3 = 3, sigmoid(3) ≈ 0.952
        assert 0.9 < level < 1.0

    def test_at_midpoint(self) -> None:
        """At the midpoint (x=0, sigmoid=0.5) the level should be ~0.5."""
        # x=0 when elapsed/adjusted = 0.5
        # With quality=1.0, adjusted=8, need elapsed=4
        level = _calculate_sigmoid_level(4.0, 8.0, 1.0)
        assert 0.4 < level < 0.6

    def test_long_elapsed(self) -> None:
        """Much longer than satisfaction hours → near 1.0."""
        level = _calculate_sigmoid_level(100.0, 8.0, 0.5)
        assert level > 0.95

    def test_low_quality_rises_faster(self) -> None:
        """Low satisfaction quality means desire rises faster."""
        level_low_q = _calculate_sigmoid_level(4.0, 8.0, 0.2)
        level_high_q = _calculate_sigmoid_level(4.0, 8.0, 0.8)
        assert level_low_q > level_high_q

    def test_social_thirst_24h(self) -> None:
        """social_thirst after 24h with default quality stays within 0-1."""
        level = _calculate_sigmoid_level(24.0, 24.0, 0.5)
        # With quality=0.5, adjusted_hours = 24 * 0.75 = 18
        # elapsed/adjusted = 24/18 ≈ 1.33, x ≈ 5.0, sigmoid ≈ 0.99
        # Actually different than naive expectation due to quality adjustment
        assert 0.0 < level < 1.0


class TestDesireEngine:
    """Tests for DesireEngine behavior."""

    @pytest.fixture
    def engine(self, tmp_path: Path) -> DesireEngine:
        return DesireEngine.from_data_dir(tmp_path)

    def test_compute_levels_returns_all_desires(self, engine: DesireEngine) -> None:
        levels = engine.compute_levels()
        assert set(levels.keys()) == set(DESIRES.keys())
        for level in levels.values():
            assert 0.0 <= level <= 1.0

    def test_compute_levels_with_modulation(self, engine: DesireEngine) -> None:
        baseline = engine.compute_levels()["curiosity"]
        modulated = engine.compute_levels_with_modulation(
            context_boosts={"curiosity": 0.1},
            emotional_modulation={"curiosity": 0.05},
            prediction_error={"curiosity": 0.08},
        )["curiosity"]
        assert modulated >= baseline

    def test_satisfy_reduces_level(self, engine: DesireEngine) -> None:
        # First, make desire high by removing last_satisfied
        engine._state["curiosity"]["last_satisfied"] = (
            datetime.now(timezone.utc) - timedelta(hours=100)
        ).isoformat()
        high = engine.compute_levels()["curiosity"]

        # Satisfy it
        new_level = engine.satisfy("curiosity", quality=0.8)
        assert new_level < high

    def test_satisfy_unknown_raises(self, engine: DesireEngine) -> None:
        with pytest.raises(ValueError, match="Unknown desire"):
            engine.satisfy("nonexistent_desire")

    def test_boost_increases_level(self, engine: DesireEngine) -> None:
        before = engine.compute_levels()["curiosity"]
        after = engine.boost("curiosity", 0.5)
        assert after >= before

    def test_boost_caps_at_one(self, engine: DesireEngine) -> None:
        engine.boost("curiosity", 0.9)
        level = engine.boost("curiosity", 0.9)
        assert level <= 1.0

    def test_boost_unknown_raises(self, engine: DesireEngine) -> None:
        with pytest.raises(ValueError, match="Unknown desire"):
            engine.boost("nonexistent_desire", 0.1)

    def test_format_summary_english(self, engine: DesireEngine) -> None:
        summary = engine.format_summary()
        assert isinstance(summary, str)
        assert len(summary) > 0
        # Should contain [high], [mid], or [low]
        import re

        assert re.search(r"\[(high|mid|low)\]", summary)

    def test_format_summary_sorted_descending(self, engine: DesireEngine) -> None:
        summary = engine.format_summary()
        parts = summary.split()
        # Extract levels from [high/mid/low]
        tag_order = {"high": 3, "mid": 2, "low": 1}
        prev_order = 4
        for part in parts:
            tag = part.split("[")[1].rstrip("]")
            order = tag_order[tag]
            assert order <= prev_order
            prev_order = order


class TestDesireRebalance:
    """Tests for rebalance values and migration."""

    @pytest.mark.parametrize(
        ("name", "hours"),
        [
            ("information_hunger", 12),
            ("social_thirst", 24),
            ("cognitive_coherence", 18),
            ("pattern_seeking", 72),
            ("predictability", 72),
            ("recognition", 36),
            ("resonance", 30),
            ("expression", 24),
            ("curiosity", 18),
        ],
    )
    def test_satisfaction_hours_rebalanced(self, name: str, hours: int) -> None:
        assert DESIRES[name]["satisfaction_hours"] == hours

    def test_0002_desire_rebalance_resets_last_satisfied_near_now(
        self, tmp_path: Path
    ) -> None:
        migration_mod = importlib.import_module("ego_mcp.migrations.0002_desire_rebalance")
        data_dir = tmp_path
        desires_path = data_dir / "desires.json"
        old_time = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        original = {
            "curiosity": {
                "last_satisfied": old_time,
                "satisfaction_quality": 0.9,
                "boost": 0.25,
            },
            "expression": {
                "last_satisfied": old_time,
                "satisfaction_quality": 0.4,
                "boost": 0.0,
            },
        }
        desires_path.write_text(
            json.dumps(original, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        before = datetime.now(timezone.utc)
        migration_mod.up(data_dir)
        after = datetime.now(timezone.utc)

        migrated = json.loads(desires_path.read_text(encoding="utf-8"))
        for name in ("curiosity", "expression"):
            updated_at = datetime.fromisoformat(migrated[name]["last_satisfied"])
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            assert before <= updated_at <= after
        assert migrated["curiosity"]["satisfaction_quality"] == 0.9
        assert migrated["curiosity"]["boost"] == 0.25
        assert migrated["expression"]["satisfaction_quality"] == 0.4
        assert migrated["expression"]["boost"] == 0.0

    def test_0002_desire_rebalance_noop_when_file_missing(self, tmp_path: Path) -> None:
        migration_mod = importlib.import_module("ego_mcp.migrations.0002_desire_rebalance")

        migration_mod.up(tmp_path)

        assert not (tmp_path / "desires.json").exists()


class TestDesirePersistence:
    """Test save/load state."""

    def test_save_and_load(self, tmp_path: Path) -> None:
        state_path = tmp_path / "desire_state.json"

        engine1 = DesireEngine.from_data_dir(tmp_path)
        engine1.satisfy("curiosity", quality=0.9)

        # New engine loads the saved state
        engine2 = DesireEngine.from_data_dir(tmp_path)
        state = engine2._state
        assert state["curiosity"]["satisfaction_quality"] == 0.9
        assert state_path.exists()

    def test_state_file_created(self, tmp_path: Path) -> None:
        DesireEngine.from_data_dir(tmp_path)
        assert (tmp_path / "desire_state.json").exists()
        assert desire_catalog_settings_path(tmp_path).exists()

    def test_corrupt_file_reinits(self, tmp_path: Path) -> None:
        state_path = tmp_path / "desire_state.json"
        state_path.write_text("corrupt json{{{")
        engine = DesireEngine.from_data_dir(tmp_path)
        # Should have reinitialized
        assert set(engine._state.keys()) == set(DESIRES.keys())

    def test_load_state_drops_unknown_fixed_desires_and_keeps_emergent(
        self,
        tmp_path: Path,
    ) -> None:
        catalog_path = desire_catalog_settings_path(tmp_path)
        payload = default_desire_catalog().model_dump(mode="json")
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        state_path = tmp_path / "desire_state.json"
        state_path.write_text(
            json.dumps(
                {
                    "legacy_fixed_desire": {
                        "last_satisfied": "2024-01-01T00:00:00+00:00",
                        "satisfaction_quality": 0.9,
                        "boost": 0.0,
                        "is_emergent": False,
                        "created": "",
                    },
                    "You want to feel safe.": {
                        "last_satisfied": "",
                        "satisfaction_quality": 0.5,
                        "boost": 0.0,
                        "is_emergent": True,
                        "created": "2024-01-01T00:00:00+00:00",
                        "satisfaction_hours": 24.0,
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        engine = DesireEngine(state_path, catalog_path=catalog_path)

        assert "legacy_fixed_desire" not in engine._state
        assert "feel_safe" in engine._state
        assert "You want to feel safe." not in engine._state

    def test_load_state_normalizes_legacy_emergent_labels(
        self,
        tmp_path: Path,
    ) -> None:
        state_path = tmp_path / "desire_state.json"
        state_path.write_text(
            json.dumps(
                {
                    "You want to grasp something.": {
                        "last_satisfied": "",
                        "satisfaction_quality": 0.5,
                        "boost": 0.0,
                        "is_emergent": True,
                        "created": (
                            datetime.now(timezone.utc) - timedelta(hours=1)
                        ).isoformat(),
                        "satisfaction_hours": 24.0,
                    }
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        engine = DesireEngine.from_data_dir(tmp_path)

        assert "grasp_something" in engine._state
        assert "You want to grasp something." not in engine._state
        assert engine.compute_levels()["grasp_something"] >= 0.0


class TestDesireCatalog:
    def test_default_catalog_matches_legacy_defaults(self) -> None:
        catalog = default_desire_catalog()
        assert catalog.legacy_desires() == DESIRES

    def test_catalog_allows_omitted_builtin_desires(self, tmp_path: Path) -> None:
        path = desire_catalog_settings_path(tmp_path)
        payload = default_desire_catalog().model_dump(mode="json")
        del payload["fixed_desires"]["social_thirst"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        catalog = load_desire_catalog(path)
        engine = DesireEngine.from_data_dir(tmp_path)

        assert "social_thirst" not in catalog.fixed_desires
        assert "social_thirst" not in engine.compute_levels()
        with pytest.raises(ValueError, match="Unknown desire: social_thirst"):
            engine.satisfy("social_thirst")

    def test_load_catalog_reports_json_decode_error_with_location(self, tmp_path: Path) -> None:
        path = desire_catalog_settings_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{broken", encoding="utf-8")

        with pytest.raises(DesireConfigurationError, match="JSON decode error at line 1 column 2"):
            load_desire_catalog(path)

    def test_load_catalog_reports_validation_paths(self, tmp_path: Path) -> None:
        path = desire_catalog_settings_path(tmp_path)
        payload = default_desire_catalog().model_dump(mode="json")
        payload["fixed_desires"]["curiosity"]["implicit_satisfaction"]["recall"] = 1.5
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        with pytest.raises(
            DesireConfigurationError,
            match="fixed_desires.curiosity: Value error, implicit_satisfaction.recall",
        ):
            load_desire_catalog(path)

    def test_load_catalog_raises_when_file_cannot_be_read(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        path = desire_catalog_settings_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

        def raise_os_error(*_args: object, **_kwargs: object) -> object:
            raise OSError("permission denied")

        monkeypatch.setattr("builtins.open", raise_os_error)

        with pytest.raises(DesireConfigurationError, match="Failed to read desire catalog"):
            load_desire_catalog(path)

    def test_custom_fixed_desire_participates_in_levels_and_blending(
        self,
        tmp_path: Path,
    ) -> None:
        path = desire_catalog_settings_path(tmp_path)
        payload = default_desire_catalog().model_dump(mode="json")
        payload["fixed_desires"]["novelty_drive"] = {
            "display_name": "novelty drive",
            "satisfaction_hours": 10,
            "maslow_level": 2,
            "sentence": {
                "rising": "You need something unfamiliar.",
                "steady": "Something new keeps tugging at you.",
                "settling": "The craving for novelty has quieted.",
            },
            "implicit_satisfaction": {"recall": 0.25},
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        engine = DesireEngine.from_data_dir(tmp_path)
        engine._state["novelty_drive"]["last_satisfied"] = (
            datetime.now(timezone.utc) - timedelta(days=10)
        ).isoformat()

        levels = engine.compute_levels()
        assert "novelty_drive" in levels
        assert engine.satisfy("novelty_drive", quality=0.8) < 1.0
        # 0.75 with default ema 0.5: 0.75 > 0.5 + 0.15 → rising
        assert (
            blend_desires(
                {"novelty_drive": 0.75},
                catalog=engine.catalog,
            )
            == "You need something unfamiliar."
        )

    def test_omitted_builtin_does_not_break_stale_implicit_rules(
        self,
        tmp_path: Path,
    ) -> None:
        path = desire_catalog_settings_path(tmp_path)
        payload = default_desire_catalog().model_dump(mode="json")
        del payload["fixed_desires"]["cognitive_coherence"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        engine = DesireEngine.from_data_dir(tmp_path)
        old_time = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        engine._state["expression"]["last_satisfied"] = old_time

        engine.satisfy_implicit("remember", category="introspection")

        assert "cognitive_coherence" not in engine.compute_levels()
        assert engine._state["expression"]["last_satisfied"] != old_time


class TestImplicitSatisfaction:
    """Tests for tool-driven implicit desire satisfaction."""

    @pytest.fixture
    def engine(self, tmp_path: Path) -> DesireEngine:
        return DesireEngine.from_data_dir(tmp_path)

    def test_recall_updates_information_hunger_and_curiosity(
        self, engine: DesireEngine
    ) -> None:
        old_time = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        engine._state["information_hunger"]["last_satisfied"] = old_time
        engine._state["curiosity"]["last_satisfied"] = old_time

        engine.satisfy_implicit("recall")

        info_last = datetime.fromisoformat(engine._state["information_hunger"]["last_satisfied"])
        cur_last = datetime.fromisoformat(engine._state["curiosity"]["last_satisfied"])
        if info_last.tzinfo is None:
            info_last = info_last.replace(tzinfo=timezone.utc)
        if cur_last.tzinfo is None:
            cur_last = cur_last.replace(tzinfo=timezone.utc)
        assert info_last > datetime.fromisoformat(old_time)
        assert cur_last > datetime.fromisoformat(old_time)
        assert engine._state["information_hunger"]["satisfaction_quality"] == 0.3
        assert engine._state["curiosity"]["satisfaction_quality"] == 0.2

    def test_remember_introspection_adds_coherence_and_expression(
        self, engine: DesireEngine
    ) -> None:
        old_time = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        engine._state["cognitive_coherence"]["last_satisfied"] = old_time
        engine._state["expression"]["last_satisfied"] = old_time

        engine.satisfy_implicit("remember", category="introspection")

        assert engine._state["cognitive_coherence"]["satisfaction_quality"] == 0.4
        assert engine._state["expression"]["satisfaction_quality"] == 0.3
        assert engine._state["cognitive_coherence"]["last_satisfied"] != old_time
        assert engine._state["expression"]["last_satisfied"] != old_time

    def test_unmapped_tool_makes_no_changes(self, engine: DesireEngine) -> None:
        before = deepcopy(engine._state)

        engine.satisfy_implicit("satisfy_desire")

        assert engine._state == before

    def test_implicit_quality_is_lower_than_explicit_default(self) -> None:
        from ego_mcp.desire import (
            IMPLICIT_SATISFACTION_MAP,
            REMEMBER_INTROSPECTION_IMPLICIT_SATISFACTION,
        )

        explicit_default_quality = 0.7
        mapped_qualities = [
            quality
            for entries in IMPLICIT_SATISFACTION_MAP.values()
            for _desire, quality in entries
        ]
        mapped_qualities.append(REMEMBER_INTROSPECTION_IMPLICIT_SATISFACTION[1])

        assert mapped_qualities
        assert all(0.0 < quality < explicit_default_quality for quality in mapped_qualities)


class TestEmergentDesires:
    @pytest.fixture
    def engine(self, tmp_path: Path) -> DesireEngine:
        return DesireEngine.from_data_dir(tmp_path)

    def test_generate_emergent_desires_from_high_confidence_notion(
        self, engine: DesireEngine
    ) -> None:
        notions = [
            Notion(
                label="friction",
                emotion_tone=Emotion.SAD,
                valence=-0.6,
                confidence=0.8,
            )
        ]

        created = engine.generate_emergent_desires(notions)

        assert created == ["be_with_someone"]
        assert engine._state[created[0]]["is_emergent"] is True
        assert engine._state[created[0]]["created"] != ""
        assert engine.compute_levels()[created[0]] >= 0.0

    def test_satisfy_accepts_legacy_emergent_sentence_alias(
        self, engine: DesireEngine
    ) -> None:
        engine._state["grasp_something"] = {
            "last_satisfied": "",
            "satisfaction_quality": 0.5,
            "boost": 0.0,
            "is_emergent": True,
            "created": (
                datetime.now(timezone.utc) - timedelta(hours=12)
            ).isoformat(),
            "satisfaction_hours": 24.0,
        }

        new_level = engine.satisfy("You want to grasp something.", quality=0.8)

        assert "You want to grasp something." not in engine._state
        assert engine._state["grasp_something"]["satisfaction_quality"] == 0.8
        assert new_level == engine.compute_levels()["grasp_something"]

    def test_blend_desires_renders_emergent_sentence_from_id(
        self, engine: DesireEngine
    ) -> None:
        assert (
            blend_desires(
                {"grasp_something": 0.8},
                catalog=engine.catalog,
            )
            == "You want to grasp something."
        )

    def test_expire_emergent_desires_removes_stale_entries(
        self, engine: DesireEngine
    ) -> None:
        stale_name = "feel_safe"
        engine._state[stale_name] = {
            "last_satisfied": "",
            "satisfaction_quality": 0.5,
            "boost": 0.0,
            "is_emergent": True,
            "created": (
                datetime.now(timezone.utc) - timedelta(hours=80)
            ).isoformat(),
            "satisfaction_hours": 24.0,
        }

        expired = engine.expire_emergent_desires()

        assert expired == [stale_name]
        assert stale_name not in engine._state

    # --- EMA tracking tests ---

    def test_ema_level_initialized_to_0_5(self, engine: DesireEngine) -> None:
        """Every fixed desire starts with ema_level=0.5."""
        for name, state in engine._state.items():
            if not state.get("is_emergent", False):
                assert state.get("ema_level") == 0.5, f"{name} missing ema_level"
                assert state.get("ema_updated_at") == "", f"{name} missing ema_updated_at"

    def test_ema_levels_property(self, engine: DesireEngine) -> None:
        """ema_levels property returns dict of {name: float}."""
        ema = engine.ema_levels
        assert isinstance(ema, dict)
        for name in DESIRES:
            assert name in ema
            assert ema[name] == 0.5

    def test_ema_updated_in_compute_levels(self, engine: DesireEngine) -> None:
        """compute_levels_with_modulation updates EMA when interval has elapsed."""
        # Set a desire to have been satisfied long ago so level is high
        engine._state["curiosity"]["last_satisfied"] = (
            datetime.now(timezone.utc) - timedelta(hours=48)
        ).isoformat()
        # Set ema_updated_at far enough in the past (>30 min)
        engine._state["curiosity"]["ema_updated_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=1)
        ).isoformat()
        engine._state["curiosity"]["ema_level"] = 0.5

        engine.compute_levels_with_modulation()

        # EMA should have moved toward the high level (alpha=0.3)
        new_ema = engine._state["curiosity"]["ema_level"]
        assert new_ema > 0.5, f"EMA should have risen toward high level, got {new_ema}"
        assert engine._state["curiosity"]["ema_updated_at"] != ""

    def test_ema_alpha_0_3_weight(self, engine: DesireEngine) -> None:
        """EMA update uses alpha=0.3: new_ema = 0.3*level + 0.7*old_ema."""
        old_ema = 0.4
        engine._state["curiosity"]["ema_level"] = old_ema
        engine._state["curiosity"]["ema_updated_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=1)
        ).isoformat()
        engine._state["curiosity"]["last_satisfied"] = (
            datetime.now(timezone.utc) - timedelta(hours=48)
        ).isoformat()

        levels = engine.compute_levels_with_modulation()
        current_level = levels["curiosity"]
        expected_ema = round(0.3 * current_level + 0.7 * old_ema, 6)
        actual_ema = round(engine._state["curiosity"]["ema_level"], 6)
        assert actual_ema == expected_ema

    def test_ema_not_updated_within_30_min(self, engine: DesireEngine) -> None:
        """EMA is NOT updated if less than 30 minutes have passed."""
        engine._state["curiosity"]["ema_level"] = 0.5
        engine._state["curiosity"]["ema_updated_at"] = (
            datetime.now(timezone.utc) - timedelta(minutes=10)
        ).isoformat()

        engine.compute_levels_with_modulation()

        assert engine._state["curiosity"]["ema_level"] == 0.5

    def test_ema_updated_after_30_min(self, engine: DesireEngine) -> None:
        """EMA IS updated if 30+ minutes have passed."""
        engine._state["curiosity"]["ema_level"] = 0.5
        engine._state["curiosity"]["ema_updated_at"] = (
            datetime.now(timezone.utc) - timedelta(minutes=31)
        ).isoformat()
        engine._state["curiosity"]["last_satisfied"] = (
            datetime.now(timezone.utc) - timedelta(hours=48)
        ).isoformat()

        engine.compute_levels_with_modulation()

        assert engine._state["curiosity"]["ema_level"] != 0.5

    def test_ema_persisted_in_state_json(self, engine: DesireEngine) -> None:
        """EMA fields survive save/load cycle."""
        engine._state["curiosity"]["ema_level"] = 0.65
        engine._state["curiosity"]["ema_updated_at"] = "2026-01-01T00:00:00+00:00"
        engine.save_state()

        engine2 = DesireEngine.from_data_dir(engine._state_path.parent)
        assert engine2._state["curiosity"]["ema_level"] == 0.65
        assert engine2._state["curiosity"]["ema_updated_at"] == "2026-01-01T00:00:00+00:00"

    def test_ema_first_call_uses_empty_updated_at(self, engine: DesireEngine) -> None:
        """When ema_updated_at is empty string, EMA should be updated on first call."""
        assert engine._state["curiosity"]["ema_updated_at"] == ""
        engine._state["curiosity"]["last_satisfied"] = (
            datetime.now(timezone.utc) - timedelta(hours=48)
        ).isoformat()

        engine.compute_levels_with_modulation()

        # First call should always update since ema_updated_at is empty
        assert engine._state["curiosity"]["ema_updated_at"] != ""
        assert engine._state["curiosity"]["ema_level"] != 0.5

    def test_expire_emergent_desires_removes_stale_satisfied_entries(
        self, engine: DesireEngine
    ) -> None:
        stale_name = "stay_in_this"
        engine._state[stale_name] = {
            "last_satisfied": (
                datetime.now(timezone.utc) - timedelta(days=8)
            ).isoformat(),
            "satisfaction_quality": 0.8,
            "boost": 0.0,
            "is_emergent": True,
            "created": (
                datetime.now(timezone.utc) - timedelta(days=10)
            ).isoformat(),
            "satisfaction_hours": 24.0,
        }

        expired = engine.expire_emergent_desires()

        assert expired == [stale_name]
        assert stale_name not in engine._state


def _memory_with_emotion(
    emotion: Emotion,
    valence: float,
    hours_ago: float = 1.0,
) -> Memory:
    ts = (
        datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    ).isoformat()
    return Memory(
        id=f"m-{emotion.value}",
        content=f"memory about {emotion.value}",
        timestamp=ts,
        emotional_trace=EmotionalTrace(
            primary=emotion,
            valence=valence,
            intensity=0.6,
        ),
    )


class TestGenerateEmergentFromRecentMemories:
    def test_fewer_than_min_memories_returns_none(self, tmp_path: Path) -> None:
        engine = DesireEngine.from_data_dir(tmp_path)
        mems = [_memory_with_emotion(Emotion.SAD, -0.5)]
        result = generate_emergent_from_recent_memories(engine, mems)
        assert result is None

    def test_negative_dominant_emotion_triggers_desire(self, tmp_path: Path) -> None:
        engine = DesireEngine.from_data_dir(tmp_path)
        mems = [
            _memory_with_emotion(Emotion.SAD, -0.6, hours_ago=1),
            _memory_with_emotion(Emotion.SAD, -0.4, hours_ago=2),
            _memory_with_emotion(Emotion.SAD, -0.5, hours_ago=3),
        ]
        result = generate_emergent_from_recent_memories(engine, mems)
        assert result is not None
        assert result == "be_with_someone"

    def test_positive_dominant_emotion_triggers_desire(self, tmp_path: Path) -> None:
        engine = DesireEngine.from_data_dir(tmp_path)
        mems = [
            _memory_with_emotion(Emotion.EXCITED, 0.7, hours_ago=1),
            _memory_with_emotion(Emotion.EXCITED, 0.5, hours_ago=2),
            _memory_with_emotion(Emotion.EXCITED, 0.6, hours_ago=3),
        ]
        result = generate_emergent_from_recent_memories(engine, mems)
        assert result is not None
        assert result == "grasp_something"

    def test_old_memories_outside_window_excluded(self, tmp_path: Path) -> None:
        engine = DesireEngine.from_data_dir(tmp_path)
        mems = [
            _memory_with_emotion(Emotion.SAD, -0.5, hours_ago=1),
            _memory_with_emotion(Emotion.SAD, -0.5, hours_ago=2),
            _memory_with_emotion(Emotion.SAD, -0.5, hours_ago=10),  # outside 6h
        ]
        result = generate_emergent_from_recent_memories(engine, mems)
        # Only 2 within window, below min_memories=3
        assert result is None

    def test_already_active_desire_not_duplicated(self, tmp_path: Path) -> None:
        engine = DesireEngine.from_data_dir(tmp_path)
        engine._state["be_with_someone"] = {
            "is_emergent": True,
            "created": datetime.now(timezone.utc).isoformat(),
            "last_satisfied": "",
            "satisfaction_quality": 0.5,
            "boost": 0.0,
            "satisfaction_hours": 24.0,
        }
        mems = [
            _memory_with_emotion(Emotion.SAD, -0.5, hours_ago=1),
            _memory_with_emotion(Emotion.SAD, -0.5, hours_ago=2),
            _memory_with_emotion(Emotion.SAD, -0.5, hours_ago=3),
        ]
        result = generate_emergent_from_recent_memories(engine, mems)
        assert result is None

    def test_mixed_emotions_uses_majority(self, tmp_path: Path) -> None:
        engine = DesireEngine.from_data_dir(tmp_path)
        mems = [
            _memory_with_emotion(Emotion.SAD, -0.5, hours_ago=1),
            _memory_with_emotion(Emotion.SAD, -0.6, hours_ago=2),
            _memory_with_emotion(Emotion.HAPPY, 0.5, hours_ago=3),
            _memory_with_emotion(Emotion.SAD, -0.4, hours_ago=4),
        ]
        result = generate_emergent_from_recent_memories(engine, mems)
        assert result == "be_with_someone"

    def test_unmapped_emotion_returns_none(self, tmp_path: Path) -> None:
        engine = DesireEngine.from_data_dir(tmp_path)
        mems = [
            _memory_with_emotion(Emotion.NEUTRAL, 0.0, hours_ago=1),
            _memory_with_emotion(Emotion.NEUTRAL, 0.0, hours_ago=2),
            _memory_with_emotion(Emotion.NEUTRAL, 0.0, hours_ago=3),
        ]
        result = generate_emergent_from_recent_memories(engine, mems)
        assert result is None

    def test_reads_min_recent_memories_from_catalog(self, tmp_path: Path) -> None:
        """min_memories defaults to catalog.emergent.min_recent_memories."""
        catalog = default_desire_catalog()
        payload = catalog.model_dump(mode="json", exclude_none=True)
        payload["emergent"]["min_recent_memories"] = 2
        settings_dir = tmp_path / "settings"
        settings_dir.mkdir()
        (settings_dir / "desires.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        engine = DesireEngine.from_data_dir(tmp_path)
        # Only 2 memories — would fail with default min_memories=3, but succeeds with 2
        mems = [
            _memory_with_emotion(Emotion.SAD, -0.5, hours_ago=1),
            _memory_with_emotion(Emotion.SAD, -0.5, hours_ago=2),
        ]
        result = generate_emergent_from_recent_memories(engine, mems)
        assert result is not None

    def test_explicit_min_memories_overrides_catalog(self, tmp_path: Path) -> None:
        engine = DesireEngine.from_data_dir(tmp_path)
        mems = [
            _memory_with_emotion(Emotion.SAD, -0.5, hours_ago=1),
            _memory_with_emotion(Emotion.SAD, -0.5, hours_ago=2),
        ]
        # Explicit override to 2 — should succeed
        result = generate_emergent_from_recent_memories(engine, mems, min_memories=2)
        assert result is not None
