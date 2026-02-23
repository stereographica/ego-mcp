# Style And Conventions

## Common Across Subprojects

- Python >=3.11, using modern typing (`list[str]`, `dict[str, Any]`, `|` unions).
- `from __future__ import annotations` used broadly.
- `mypy` strict mode in both `ego-mcp` and `dashboard`.
- Build system: Hatchling for both Python packages.
- Dependency management: `uv`.
- Linting: `ruff` in both subprojects.

## ego-mcp Specifics

- ruff: line-length=88, target-version py311.
- isort for import sorting (checked in CI via `isort --check-only`).
- Async-first APIs for MCP handlers and memory operations.
- Prefers `@dataclass` for structured domain objects.
- Config is immutable (`@dataclass(frozen=True)`) created via `from_env()`.
- Enums are string-based (`class X(str, Enum)`) for stable serialization.
- Tool definitions grouped as constants before handlers.
- Module/function names: `snake_case`; class names: `PascalCase`.
- Internal helpers may start with `_`.
- Module docstrings present; public functions have concise docstrings.
- Testing: `pytest` with `pytest-asyncio`, `asyncio_mode = "auto"`.
- Test classes group related behavior.

## dashboard Backend Specifics

- ruff: line-length=100, target-version py311, select rules: E, F, I, UP.
- ruff format enforced (in addition to lint).
- FastAPI application pattern.
- `pydantic>=2.11` for models and settings.
- `pytest` with `pythonpath = ["src"]`.

## dashboard Frontend Specifics

- React 19 + TypeScript ~5.9.
- Vite 7 for build, Vitest for tests.
- ESLint 9 + Prettier for code quality.
- Tailwind CSS via tailwind-merge + clsx utility pattern.
- Component library: Radix UI (tabs), Lucide React (icons), Recharts (charts).

## Practical Guidance

- Keep new code strictly typed and mypy-clean.
- Match existing dataclass + enum patterns for new domain entities in ego-mcp.
- Follow concise docstring style already used across modules.
- Respect different ruff line-length settings per subproject (88 vs 100).