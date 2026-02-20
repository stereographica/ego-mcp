"""Workspace Markdown synchronization for OpenClaw memory files."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ego_mcp.types import Category, Memory


CURATION_CATEGORIES = {
    Category.INTROSPECTION,
    Category.RELATIONSHIP,
    Category.SELF_DISCOVERY,
    Category.LESSON,
}


@dataclass(frozen=True)
class SyncResult:
    """Summary of workspace sync updates."""

    daily_updated: bool
    latest_monologue_updated: bool
    curated_updated: bool


class WorkspaceMemorySync:
    """Sync introspection and memory entries to OpenClaw workspace files."""

    def __init__(self, workspace_dir: Path) -> None:
        self._workspace_dir = workspace_dir
        self._memory_dir = workspace_dir / "memory"
        self._latest_monologue = self._memory_dir / "inner-monologue-latest.md"
        self._curated_memory = workspace_dir / "MEMORY.md"

    @property
    def workspace_dir(self) -> Path:
        return self._workspace_dir

    @staticmethod
    def from_optional_path(workspace_dir: Path | None) -> WorkspaceMemorySync | None:
        """Build sync helper only when a workspace directory is provided."""
        if workspace_dir is None:
            return None
        return WorkspaceMemorySync(workspace_dir)

    def read_latest_monologue(self) -> tuple[str | None, str | None]:
        """Read latest monologue text and optional updated timestamp."""
        if not self._latest_monologue.exists():
            return None, None

        text = self._latest_monologue.read_text(encoding="utf-8").strip()
        if not text:
            return None, None

        updated: str | None = None
        content = text
        lines = text.splitlines()
        if len(lines) >= 4 and lines[0].startswith("# "):
            if lines[2].startswith("Updated: "):
                updated = lines[2][len("Updated: ") :].strip()
            content = "\n".join(lines[4:]).strip()
            if not content:
                content = text
        return content, updated

    def sync_memory(self, memory: Memory) -> SyncResult:
        """Append memory to daily log and update related workspace artifacts."""
        self._memory_dir.mkdir(parents=True, exist_ok=True)

        daily_updated = self._append_daily_log(memory)
        latest_updated = False
        if memory.category == Category.INTROSPECTION:
            self.write_latest_monologue(memory.content, memory.timestamp)
            latest_updated = True

        curated_updated = self._append_curated(memory)
        return SyncResult(
            daily_updated=daily_updated,
            latest_monologue_updated=latest_updated,
            curated_updated=curated_updated,
        )

    def write_latest_monologue(self, content: str, timestamp: str) -> None:
        """Write the latest introspection text for session resume."""
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        normalized = content.strip()
        if not normalized:
            return

        payload = f"# Latest Inner Monologue\n\nUpdated: {timestamp}\n\n{normalized}\n"
        self._latest_monologue.write_text(payload, encoding="utf-8")

    def _append_daily_log(self, memory: Memory) -> bool:
        date_str, time_str = _timestamp_parts(memory.timestamp)
        daily_file = self._memory_dir / f"{date_str}.md"

        if daily_file.exists():
            current = daily_file.read_text(encoding="utf-8")
        else:
            current = f"# Memory Log {date_str}\n\n"

        marker = f"[id:{memory.id}]"
        if marker in current:
            return False

        content = memory.content.replace("\n", " ").strip()
        entry = (
            f"- {time_str} [{memory.category.value}] {content} "
            f"(emotion: {memory.emotional_trace.primary.value}, "
            f"intensity: {memory.emotional_trace.intensity:.2f}) {marker}\n"
        )
        daily_file.write_text(current + entry, encoding="utf-8")
        return True

    def _append_curated(self, memory: Memory) -> bool:
        if memory.importance < 4 and memory.category not in CURATION_CATEGORIES:
            return False

        if self._curated_memory.exists():
            current = self._curated_memory.read_text(encoding="utf-8")
        else:
            current = "# Curated Memory\n\n"

        marker = f"[id:{memory.id}]"
        if marker in current:
            return False

        date_str, _ = _timestamp_parts(memory.timestamp)
        short = memory.content.replace("\n", " ").strip()
        if len(short) > 180:
            short = short[:177].rstrip() + "..."

        entry = (
            f"- [{date_str}] ({memory.category.value}) {short} "
            f"(emotion: {memory.emotional_trace.primary.value}) {marker}\n"
        )
        self._curated_memory.write_text(current + entry, encoding="utf-8")
        return True


def _timestamp_parts(timestamp: str) -> tuple[str, str]:
    """Extract date/time strings in UTC-ish format for Markdown logs."""
    try:
        parsed = datetime.fromisoformat(timestamp)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        parsed = datetime.now(timezone.utc)
    return parsed.strftime("%Y-%m-%d"), parsed.strftime("%H:%M")
