"""Tests for DesireEngine."""

from __future__ import annotations

import importlib
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ego_mcp.desire import DESIRES, DesireEngine, _calculate_sigmoid_level


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
        state_path = tmp_path / "desires.json"
        return DesireEngine(state_path)

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
        state_path = tmp_path / "desires.json"

        engine1 = DesireEngine(state_path)
        engine1.satisfy("curiosity", quality=0.9)

        # New engine loads the saved state
        engine2 = DesireEngine(state_path)
        state = engine2._state
        assert state["curiosity"]["satisfaction_quality"] == 0.9

    def test_state_file_created(self, tmp_path: Path) -> None:
        state_path = tmp_path / "desires.json"
        DesireEngine(state_path)
        assert state_path.exists()

    def test_corrupt_file_reinits(self, tmp_path: Path) -> None:
        state_path = tmp_path / "desires.json"
        state_path.write_text("corrupt json{{{")
        engine = DesireEngine(state_path)
        # Should have reinitialized
        assert set(engine._state.keys()) == set(DESIRES.keys())


class TestImplicitSatisfaction:
    """Tests for tool-driven implicit desire satisfaction."""

    @pytest.fixture
    def engine(self, tmp_path: Path) -> DesireEngine:
        return DesireEngine(tmp_path / "desires.json")

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
