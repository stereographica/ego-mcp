# Style And Conventions

## Language/Typing

- Uses modern Python typing (`list[str]`, `dict[str, Any]`, `|` unions).
- `from __future__ import annotations` is used broadly.
- `mypy` is configured with `strict = true`; maintain full type coverage.
- Async-first APIs are used for MCP handlers and memory operations.

## Data Modeling

- Prefers `@dataclass` for structured domain objects (`types.py`, `config.py`).
- Enums are string-based (`class X(str, Enum)`) for stable serialization.
- Config is immutable (`@dataclass(frozen=True)`) and created via `from_env()`.

## Naming / Organization

- Module/function names are `snake_case`; class names `PascalCase`.
- Internal helper names may start with `_` (e.g., `_dispatch`, `_get_config`).
- Tool definitions are grouped as constants (`SURFACE_TOOLS`, `BACKEND_TOOLS`) before handlers.

## Documentation / Comments

- Module docstrings are present in source files.
- Public functions/classes generally have concise docstrings.
- Inline comments are used sparingly, mainly for logical sectioning.

## Testing Style

- `pytest` fixtures for setup and environment isolation.
- Test classes group related behavior (`TestValidation`, `TestFrozen`, etc.).
- Async tests use `@pytest.mark.asyncio`.

## Practical Guidance

- Keep new code strictly typed and mypy-clean.
- Match existing dataclass + enum patterns for new domain entities.
- Follow concise docstring style already used across modules.