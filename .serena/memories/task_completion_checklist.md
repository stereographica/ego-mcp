# Task Completion Checklist

When finishing code changes in `ego-mcp`:

1. Run tests: `uv run pytest tests/ -v`
2. Run static typing: `uv run mypy src/ego_mcp/`
3. Validate runtime entrypoint when relevant: `uv run python -m ego_mcp`
4. Confirm environment requirements are still documented (provider + API key vars).
5. Review diff quality (`git diff`) and ensure no accidental unrelated edits.

Notes:
- No formatter/linter command is explicitly configured in `pyproject.toml` (no ruff/black config found).
- Strict mypy is the main static quality gate; keep annotations and return types complete.