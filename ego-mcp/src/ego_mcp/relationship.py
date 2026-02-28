"""Relationship model persistence and updates."""

from __future__ import annotations

import dataclasses
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ego_mcp.types import RelationshipModel

_UPDATABLE_FIELDS = frozenset(
    field.name
    for field in dataclasses.fields(RelationshipModel)
    if field.name not in ("person_id",)
)


class RelationshipStore:
    """JSON-backed store for per-person relationship models."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            self._data = {}
            return
        try:
            parsed = json.loads(self._path.read_text(encoding="utf-8"))
            self._data = parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, OSError):
            self._data = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _default_model(person_id: str) -> dict[str, Any]:
        model = RelationshipModel(person_id=person_id, name=person_id)
        data = asdict(model)
        data["interaction_log"] = []
        return data

    def _get_raw(self, person_id: str) -> dict[str, Any]:
        return dict(self._data.get(person_id, self._default_model(person_id)))

    def get(self, person_id: str) -> RelationshipModel:
        raw = self._get_raw(person_id)
        return RelationshipModel(
            person_id=person_id,
            name=str(raw.get("name", person_id)),
            known_facts=list(raw.get("known_facts", [])),
            communication_style=dict(raw.get("communication_style", {})),
            preferred_topics=list(raw.get("preferred_topics", [])),
            sensitive_topics=list(raw.get("sensitive_topics", [])),
            emotional_baseline=dict(raw.get("emotional_baseline", {})),
            trust_level=float(raw.get("trust_level", 0.5)),
            shared_episode_ids=list(raw.get("shared_episode_ids", [])),
            inferred_personality=dict(raw.get("inferred_personality", {})),
            recent_mood_trajectory=list(raw.get("recent_mood_trajectory", [])),
            first_interaction=str(raw.get("first_interaction", "")),
            last_interaction=str(raw.get("last_interaction", "")),
            total_interactions=int(raw.get("total_interactions", 0)),
        )

    def update(self, person_id: str, patch: dict[str, Any]) -> RelationshipModel:
        invalid_fields = sorted(key for key in patch if key not in _UPDATABLE_FIELDS)
        if invalid_fields:
            valid_fields = ", ".join(sorted(_UPDATABLE_FIELDS))
            invalid = ", ".join(invalid_fields)
            raise ValueError(
                f"Invalid relationship field(s): {invalid}. "
                f"Valid fields: {valid_fields}"
            )
        raw = self._get_raw(person_id)
        for key, value in patch.items():
            raw[key] = value
        self._data[person_id] = raw
        self._save()
        return self.get(person_id)

    def add_interaction(
        self, person_id: str, timestamp: str, tone: str
    ) -> RelationshipModel:
        raw = self._get_raw(person_id)
        interaction_log = raw.get("interaction_log", [])
        if not isinstance(interaction_log, list):
            interaction_log = []
        interaction_log.append({"timestamp": timestamp, "tone": tone})
        raw["interaction_log"] = interaction_log
        raw["total_interactions"] = len(interaction_log)

        if not raw.get("first_interaction"):
            raw["first_interaction"] = timestamp
        raw["last_interaction"] = timestamp

        communication_style = raw.get("communication_style", {})
        if not isinstance(communication_style, dict):
            communication_style = {}
        communication_style[tone] = float(communication_style.get(tone, 0.0)) + 1.0
        raw["communication_style"] = communication_style

        trajectory = raw.get("recent_mood_trajectory", [])
        if not isinstance(trajectory, list):
            trajectory = []
        trajectory.append({"timestamp": timestamp, "mood": tone})
        raw["recent_mood_trajectory"] = trajectory[-20:]

        self._data[person_id] = raw
        self._save()
        return self.get(person_id)

    def add_shared_episode(self, person_id: str, episode_id: str) -> RelationshipModel:
        raw = self._get_raw(person_id)
        episode_ids = raw.get("shared_episode_ids", [])
        if not isinstance(episode_ids, list):
            episode_ids = []
        if episode_id not in episode_ids:
            episode_ids.append(episode_id)
        raw["shared_episode_ids"] = episode_ids
        self._data[person_id] = raw
        self._save()
        return self.get(person_id)

    def apply_tom_feedback(
        self,
        person_id: str,
        dominant_tone: str,
        preferred_topics: list[str],
        sensitive_topics: list[str],
    ) -> RelationshipModel:
        """Update model fields inferred from recent ToM analysis."""
        raw = self._get_raw(person_id)
        now = datetime.now(timezone.utc).isoformat()

        if dominant_tone and dominant_tone != "unknown tone":
            trajectory = raw.get("recent_mood_trajectory", [])
            if not isinstance(trajectory, list):
                trajectory = []
            trajectory.append({"timestamp": now, "mood": dominant_tone})
            raw["recent_mood_trajectory"] = trajectory[-20:]

        if preferred_topics:
            raw["preferred_topics"] = preferred_topics
        if sensitive_topics:
            raw["sensitive_topics"] = sensitive_topics

        self._data[person_id] = raw
        self._save()
        return self.get(person_id)
