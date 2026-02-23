# Task Completion Checklist

## When finishing code changes in `ego-mcp/`

1. Run tests: `cd ego-mcp && GEMINI_API_KEY=test-key uv run pytest tests -v`
2. Run isort check: `uv run isort --check-only src tests`
3. Run linter: `uv run ruff check src tests`
4. Run type checker: `uv run mypy src tests`
5. Validate entrypoint when relevant: `uv run python -m ego_mcp`
6. Confirm environment requirements still documented (provider + API key vars).
7. Review diff (`git diff`) — no accidental unrelated edits.

## When finishing code changes in `dashboard/` backend

1. Run tests: `cd dashboard && uv run pytest -v`
2. Run linter: `uv run ruff check src tests`
3. Run format check: `uv run ruff format --check src tests`
4. Run type checker: `uv run mypy src tests`
5. Review diff.

## When finishing code changes in `dashboard/frontend/`

1. Lint: `cd dashboard/frontend && npm run lint`
2. Format check: `npm run format:check`
3. Tests: `npm run test`
4. Build: `npm run build`
5. Review diff.

## When finishing docker-compose changes

1. Validate: `cd dashboard && docker compose config`

## General Notes

- Both Python subprojects use strict mypy — keep annotations and return types complete.
- `ego-mcp` uses ruff with line-length=88; `dashboard` uses line-length=100.
- `dashboard` additionally enforces `ruff format` (not just lint).
- Do not conclude work while any CI check is failing.