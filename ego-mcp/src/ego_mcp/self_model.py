"""Self model persistence and question management."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ego_mcp.types import SelfModel


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
        question_log = self._data.get("question_log", [])
        unresolved_texts: list[str] = []
        if isinstance(question_log, list):
            unresolved_ids = set(unresolved if isinstance(unresolved, list) else [])
            for item in question_log:
                if (
                    isinstance(item, dict)
                    and item.get("id") in unresolved_ids
                    and isinstance(item.get("question"), str)
                ):
                    unresolved_texts.append(item["question"])

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

    def add_question(self, question: str) -> str:
        question_id = f"q_{uuid.uuid4().hex[:10]}"
        question_log = self._data.get("question_log", [])
        if not isinstance(question_log, list):
            question_log = []
        question_log.append({"id": question_id, "question": question, "resolved": False})
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

        self._data["unresolved_questions"] = [qid for qid in unresolved if qid != question_id]
        question_log = self._data.get("question_log", [])
        if isinstance(question_log, list):
            for item in question_log:
                if isinstance(item, dict) and item.get("id") == question_id:
                    item["resolved"] = True
                    break
        self._data["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._save()
        return True
