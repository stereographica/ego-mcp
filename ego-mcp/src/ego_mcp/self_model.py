"""Self model persistence and question management."""

from __future__ import annotations

import dataclasses
import json
import math
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ego_mcp import timezone_utils
from ego_mcp.types import SelfModel

_UPDATABLE_FIELDS = frozenset(
    f.name for f in dataclasses.fields(SelfModel) if f.name not in ("last_updated",)
)

_FIELD_TYPES: dict[str, type | tuple[type, ...]] = {
    "preferences": dict,
    "discovered_values": dict,
    "skill_confidence": dict,
    "current_goals": list,
    "unresolved_questions": list,
    "identity_narratives": list,
    "growth_log": list,
    "confidence_calibration": (int, float),
}

QUESTION_ACTIVE_MIN_SALIENCE = 0.3
QUESTION_DORMANT_MAX_SALIENCE = 0.1


def _clamp_question_importance(value: Any) -> int:
    """Clamp question importance to the supported 1-5 range."""
    try:
        importance = int(value)
    except (TypeError, ValueError):
        importance = 3
    return max(1, min(5, importance))


def _parse_question_timestamp(timestamp: str) -> datetime | None:
    """Parse ISO8601 timestamp for question metadata; returns None if invalid."""
    if not timestamp:
        return None
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone_utils.app_timezone())
    return parsed


def _age_days_since(timestamp: str, now: datetime | None = None) -> float:
    """Return age in days for a stored question timestamp."""
    parsed = _parse_question_timestamp(timestamp)
    if parsed is None:
        return 0.0
    if now is None:
        now = timezone_utils.now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone_utils.app_timezone())
    delta = (now - parsed).total_seconds()
    if delta <= 0:
        return 0.0
    return delta / 86400.0


def _calculate_salience(importance: int, age_days: float) -> float:
    """Decay question salience based on importance and age."""
    clamped_importance = _clamp_question_importance(importance)
    half_life = clamped_importance * 14
    if half_life <= 0:
        return 0.0
    salience = (clamped_importance / 5.0) * math.exp(-age_days / half_life)
    return max(0.0, min(1.0, salience))


class SelfModelStore:
    """JSON-backed store for self model."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict[str, Any] = {}
        self._load()

    def _default_data(self) -> dict[str, Any]:
        model = SelfModel()
        data = asdict(model)
        data["unresolved_questions"] = []
        data["question_log"] = []
        data["last_updated"] = timezone_utils.now().isoformat()
        return data

    def _load(self) -> None:
        if not self._path.exists():
            self._data = self._default_data()
            return
        try:
            parsed = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(parsed, dict):
                self._data = self._default_data()
            else:
                self._data = {**self._default_data(), **parsed}
                self._rescue_orphan_unresolved_questions()
        except (json.JSONDecodeError, OSError):
            self._data = self._default_data()

    def _rescue_orphan_unresolved_questions(self) -> None:
        unresolved = self._data.get("unresolved_questions", [])
        if not isinstance(unresolved, list):
            return

        question_log = self._data.get("question_log", [])
        changed = False
        if not isinstance(question_log, list):
            question_log = []
            self._data["question_log"] = question_log
            changed = True

        normalized_log = self.get_question_log()
        known_ids = {str(entry["id"]) for entry in normalized_log}
        text_to_id = {
            str(entry["question"]): str(entry["id"])
            for entry in normalized_log
            if not bool(entry.get("resolved", False))
        }

        rescued: list[str] = []
        for item in unresolved:
            raw = str(item)
            if raw in known_ids:
                question_id = raw
            elif raw in text_to_id:
                question_id = text_to_id[raw]
                changed = True
            else:
                question_id = f"q_{uuid.uuid4().hex[:10]}"
                now_iso = timezone_utils.now().isoformat()
                question_log.append(
                    {
                        "id": question_id,
                        "question": raw,
                        "resolved": False,
                        "importance": 3,
                        "created_at": now_iso,
                        "person_id": None,
                        "companions": [],
                        "lineage": [],
                        "last_fed_at": "",
                    }
                )
                known_ids.add(question_id)
                text_to_id[raw] = question_id
                changed = True
            rescued.append(question_id)

        if rescued != unresolved:
            changed = True
        if changed:
            self._data["unresolved_questions"] = rescued
            self._data["last_updated"] = timezone_utils.now().isoformat()
            self._save()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self) -> SelfModel:
        unresolved = self._data.get("unresolved_questions", [])
        unresolved_texts: list[str] = []
        unresolved_ids = (
            [str(qid) for qid in unresolved] if isinstance(unresolved, list) else []
        )
        question_by_id = {
            str(item["id"]): str(item["question"])
            for item in self.get_question_log()
            if isinstance(item.get("question"), str)
        }
        seen_unresolved: set[str] = set()
        for question_id in unresolved_ids:
            if question_id in seen_unresolved:
                continue
            seen_unresolved.add(question_id)
            question = question_by_id.get(question_id)
            if question is not None:
                unresolved_texts.append(question)

        return SelfModel(
            preferences=dict(self._data.get("preferences", {})),
            discovered_values=dict(self._data.get("discovered_values", {})),
            skill_confidence=dict(self._data.get("skill_confidence", {})),
            current_goals=list(self._data.get("current_goals", [])),
            unresolved_questions=unresolved_texts,
            identity_narratives=list(self._data.get("identity_narratives", [])),
            growth_log=list(self._data.get("growth_log", [])),
            confidence_calibration=float(self._data.get("confidence_calibration", 0.5)),
            last_updated=str(self._data.get("last_updated", "")),
        )

    def update(self, patch: dict[str, Any]) -> SelfModel:
        invalid_fields = sorted(key for key in patch if key not in _UPDATABLE_FIELDS)
        if invalid_fields:
            valid_fields = ", ".join(sorted(_UPDATABLE_FIELDS))
            invalid = ", ".join(invalid_fields)
            raise ValueError(
                f"Invalid self-model field(s): {invalid}. "
                f"Valid fields: {valid_fields}"
            )
        for key, value in patch.items():
            expected = _FIELD_TYPES.get(key)
            if expected is not None and not isinstance(value, expected):
                raise TypeError(
                    f"Field '{key}' expects {expected.__name__ if isinstance(expected, type) else ' or '.join(t.__name__ for t in expected)}, "
                    f"got {type(value).__name__}: {value!r}"
                )
        for key, value in patch.items():
            self._data[key] = value
        self._data["last_updated"] = timezone_utils.now().isoformat()
        self._save()
        return self.get()

    def get_question_log(self) -> list[dict[str, Any]]:
        """Return normalized question log entries with backward-compatible defaults."""
        raw = self._data.get("question_log", [])
        if not isinstance(raw, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            question = item.get("question")
            if not isinstance(question, str):
                continue
            entry = dict(item)
            entry["id"] = str(item.get("id", ""))
            entry["question"] = question
            entry["resolved"] = bool(item.get("resolved", False))
            entry["importance"] = _clamp_question_importance(item.get("importance", 3))
            created_at = item.get("created_at", "")
            entry["created_at"] = created_at if isinstance(created_at, str) else ""
            person_id = item.get("person_id")
            entry["person_id"] = (
                person_id if isinstance(person_id, str) and person_id else None
            )
            companions = item.get("companions", [])
            entry["companions"] = (
                [dict(companion) for companion in companions if isinstance(companion, dict)]
                if isinstance(companions, list)
                else []
            )
            lineage = item.get("lineage", [])
            entry["lineage"] = (
                [str(question_id) for question_id in lineage if isinstance(question_id, str)]
                if isinstance(lineage, list)
                else []
            )
            last_fed_at = item.get("last_fed_at", "")
            entry["last_fed_at"] = (
                last_fed_at if isinstance(last_fed_at, str) else ""
            )
            normalized.append(entry)
        return normalized

    def add_question(
        self,
        question: str,
        importance: int = 3,
        *,
        person_id: str | None = None,
        lineage: list[str] | None = None,
    ) -> str:
        question_id = f"q_{uuid.uuid4().hex[:10]}"
        question_log = self._data.get("question_log", [])
        if not isinstance(question_log, list):
            question_log = []
        now_iso = timezone_utils.now().isoformat()
        question_log.append(
            {
                "id": question_id,
                "question": question,
                "resolved": False,
                "importance": _clamp_question_importance(importance),
                "created_at": now_iso,
                "person_id": person_id,
                "companions": [],
                "lineage": list(lineage or []),
                "last_fed_at": "",
            }
        )
        self._data["question_log"] = question_log

        unresolved = self._data.get("unresolved_questions", [])
        if not isinstance(unresolved, list):
            unresolved = []
        unresolved.append(question_id)
        self._data["unresolved_questions"] = unresolved
        self._data["last_updated"] = timezone_utils.now().isoformat()

        self._save()
        return question_id

    def update_question_fields(self, question_id: str, updates: dict[str, Any]) -> bool:
        """Update stored question metadata by id."""
        question_log = self._data.get("question_log", [])
        if not isinstance(question_log, list):
            return False

        for item in question_log:
            if isinstance(item, dict) and item.get("id") == question_id:
                item.update(updates)
                self._data["last_updated"] = timezone_utils.now().isoformat()
                self._save()
                return True
        return False

    def resolve_question(self, question_id: str) -> bool:
        unresolved = self._data.get("unresolved_questions", [])
        if not isinstance(unresolved, list) or question_id not in unresolved:
            return False

        self._data["unresolved_questions"] = [
            qid for qid in unresolved if qid != question_id
        ]
        question_log = self._data.get("question_log", [])
        if isinstance(question_log, list):
            for item in question_log:
                if isinstance(item, dict) and item.get("id") == question_id:
                    item["resolved"] = True
                    break
        self._data["last_updated"] = timezone_utils.now().isoformat()
        self._save()
        return True

    def update_question_importance(self, question_id: str, importance: int) -> bool:
        """Update question importance in-place by id."""
        question_log = self._data.get("question_log", [])
        if not isinstance(question_log, list):
            return False

        for item in question_log:
            if isinstance(item, dict) and item.get("id") == question_id:
                item["importance"] = _clamp_question_importance(importance)
                self._data["last_updated"] = timezone_utils.now().isoformat()
                self._save()
                return True
        return False

    def get_visible_questions(
        self, max_active: int = 5, max_resurfacing: int = 2
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Return active and resurfacing unresolved questions ordered by salience."""
        enriched = self.get_unresolved_questions_with_salience()
        active = [
            item
            for item in enriched
            if float(item.get("salience", 0.0)) > QUESTION_ACTIVE_MIN_SALIENCE
        ]
        resurfacing = [
            item
            for item in enriched
            if QUESTION_DORMANT_MAX_SALIENCE
            < float(item.get("salience", 0.0))
            <= QUESTION_ACTIVE_MIN_SALIENCE
        ]
        active.sort(key=lambda item: float(item.get("salience", 0.0)), reverse=True)
        resurfacing.sort(key=lambda item: float(item.get("salience", 0.0)), reverse=True)
        return active[:max_active], resurfacing[:max_resurfacing]

    def get_unresolved_questions_with_salience(self) -> list[dict[str, Any]]:
        """Return all unresolved questions enriched with salience and age metadata."""
        now = timezone_utils.now()

        unresolved_ids_raw = self._data.get("unresolved_questions", [])
        unresolved_ids = (
            set(str(qid) for qid in unresolved_ids_raw)
            if isinstance(unresolved_ids_raw, list)
            else set()
        )
        enriched_questions: list[dict[str, Any]] = []

        for entry in self.get_question_log():
            if entry.get("resolved", False):
                continue
            entry_id = str(entry.get("id", ""))
            if unresolved_ids and entry_id not in unresolved_ids:
                continue
            importance = _clamp_question_importance(entry.get("importance", 3))
            created_at = str(entry.get("created_at", ""))
            age_days = _age_days_since(created_at, now=now)
            salience = _calculate_salience(importance, age_days)
            enriched = {
                **entry,
                "importance": importance,
                "created_at": created_at,
                "salience": salience,
                "age_days": age_days,
            }
            enriched_questions.append(enriched)

        enriched_questions.sort(
            key=lambda item: float(item.get("salience", 0.0)), reverse=True
        )
        return enriched_questions
