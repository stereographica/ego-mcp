# 001: Python プロジェクト初期化

## 目的
`ego-mcp/` に Python プロジェクトを作成する。

## 成果物

```
ego-mcp/
├── pyproject.toml
├── src/ego_mcp/
│   ├── __init__.py      # __version__ = "0.1.0"
│   ├── __main__.py      # asyncio.run(main())
│   └── server.py        # 空の MCP サーバー (mcp.server.Server + stdio_server)
└── tests/
    ├── __init__.py
    └── conftest.py
```

## 仕様
- `pyproject.toml`: name=`ego-mcp`, python>=3.11, build=hatchling
- 依存: `mcp>=1.0.0`, `chromadb>=0.5.0`, `httpx>=0.27.0`, `psutil>=5.9.0`
- dev 依存: `pytest>=8.0.0`, `pytest-asyncio>=0.23.0`, `respx>=0.20.0`, `mypy>=1.8.0`
- `server.py`: `mcp.server.Server("ego-mcp")` を作成し `stdio_server` で提供。ツール登録なし

## 完了確認

```bash
cd ego-mcp
pip install -e ".[dev]"
python -c "import ego_mcp; print(ego_mcp.__version__)"  # → 0.1.0
timeout 3 python -m ego_mcp || true                      # → Starting ego-mcp server...
pytest tests/                                            # → no tests ran
```
