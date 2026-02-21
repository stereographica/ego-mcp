# AGENTS.md

This workspace uses `ego-mcp` as the primary MCP server project.

## Scope

- Main project path: `ego-mcp/`
- Python package: `src/ego_mcp`
- Runtime entrypoint: `python -m ego_mcp`

## Setup

```bash
cd ego-mcp
uv sync --dev
```

Required environment variables (choose one provider):

```bash
export GEMINI_API_KEY="your-gemini-api-key"
# or
export EGO_MCP_EMBEDDING_PROVIDER="openai"
export OPENAI_API_KEY="your-openai-api-key"
```

## Verify

```bash
cd ego-mcp
uv run python -c "import ego_mcp; print(ego_mcp.__version__)"
uv run python -m ego_mcp
```

## Tool Usage Flow (Minimal)

- Session start: `wake_up` -> `introspect` -> save reflection with `remember`
- Heartbeat: `feel_desires` -> if needed `introspect` -> act or `HEARTBEAT_OK`
- Before important responses: `consider_them` -> `am_i_being_genuine`
- After significant experiences: `remember`

## Development Commands

```bash
cd ego-mcp
uv run pytest tests/ -v
uv run mypy src/ego_mcp/
```

## Mandatory CI Gate After Code Changes

If any code under `ego-mcp/` is changed, run all checks defined in
`.github/workflows/ego-mcp-ci.yml` before finishing work.

Required sequence:

```bash
cd ego-mcp
uv sync --extra dev
GEMINI_API_KEY=test-key uv run pytest tests -v
uv run ruff check src tests
uv run mypy src tests
```

Rule:
- Do not conclude the task while any check is failing.
- Fix issues and rerun the failed checks until all required checks pass.

## Troubleshooting: `hashlib blake2*` with `uv`

If `uv` shows `unsupported hash type blake2b/blake2s`, a broken Python (often `pyenv`) is being selected.

```bash
cd ego-mcp
rm -rf .venv
uv sync --dev
```

This repo pins Python via `ego-mcp/.python-version` (`3.14`).
If needed, run once with an explicit interpreter:

```bash
uv run --python /opt/homebrew/bin/python3.14 python -c "import hashlib; print(hasattr(hashlib, 'blake2b'))"
```
