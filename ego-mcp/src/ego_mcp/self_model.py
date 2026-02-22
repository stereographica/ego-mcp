"""Self model persistence and question management."""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ego_mcp.types import SelfModel


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
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _age_days_since(timestamp: str, now: datetime | None = None) -> float:
    """Return age in days for a stored question timestamp."""
    parsed = _parse_question_timestamp(timestamp)
    if parsed is None:
        return 0.0
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
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
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
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
        except (json.JSONDecodeError, OSError):
            self._data = self._default_data()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self) -> SelfModel:
        unresolved = self._data.get("unresolved_questions", [])
        unresolved_texts: list[str] = []
        unresolved_ids = set(unresolved if isinstance(unresolved, list) else [])
        for item in self.get_question_log():
            if item.get("id") in unresolved_ids and isinstance(item.get("question"), str):
                unresolved_texts.append(str(item["question"]))

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
        for key, value in patch.items():
            self._data[key] = value
        self._data["last_updated"] = datetime.now(timezone.utc).isoformat()
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
            normalized.append(entry)
        return normalized

    def add_question(self, question: str, importance: int = 3) -> str:
        question_id = f"q_{uuid.uuid4().hex[:10]}"
        question_log = self._data.get("question_log", [])
        if not isinstance(question_log, list):
            question_log = []
        now_iso = datetime.now(timezone.utc).isoformat()
        question_log.append(
            {
                "id": question_id,
                "question": question,
                "resolved": False,
                "importance": _clamp_question_importance(importance),
                "created_at": now_iso,
            }
        )
        self._data["question_log"] = question_log

        unresolved = self._data.get("unresolved_questions", [])
        if not isinstance(unresolved, list):
            unresolved = []
        unresolved.append(question_id)
        self._data["unresolved_questions"] = unresolved
        self._data["last_updated"] = datetime.now(timezone.utc).isoformat()

        self._save()
        return question_id

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
        self._data["last_updated"] = datetime.now(timezone.utc).isoformat()
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
                self._data["last_updated"] = datetime.now(timezone.utc).isoformat()
                self._save()
                return True
        return False

    def get_visible_questions(
        self, max_active: int = 5, max_resurfacing: int = 2
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Return active and resurfacing unresolved questions ordered by salience."""
        enriched = self.get_unresolved_questions_with_salience()
        active = [
            item for item in enriched if float(item.get("salience", 0.0)) > 0.3
        ]
        resurfacing = [
            item
            for item in enriched
            if 0.1 < float(item.get("salience", 0.0)) <= 0.3
        ]
        active.sort(key=lambda item: float(item.get("salience", 0.0)), reverse=True)
        resurfacing.sort(key=lambda item: float(item.get("salience", 0.0)), reverse=True)
        return active[:max_active], resurfacing[:max_resurfacing]

    def get_unresolved_questions_with_salience(self) -> list[dict[str, Any]]:
        """Return all unresolved questions enriched with salience and age metadata."""
        now = datetime.now(timezone.utc)

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
