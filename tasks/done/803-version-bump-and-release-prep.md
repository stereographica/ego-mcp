# 803: バージョンアップと CI 全チェック

## 目的
800〜802 の変更を含めてバージョンを v0.2.2 に更新し、CI チェックを全て通す。

## 前提
- 800〜802 が全て完了していること

## 参照
- `design/memory-dedup-design.md`（実装スコープ > バージョニング）
- `CLAUDE.md`（ego-mcp リリースワークフロー）

## タスク

### T-803-1: バージョン番号の更新
対象ファイル: `ego-mcp/pyproject.toml`, `ego-mcp/src/ego_mcp/__init__.py`

両ファイルのバージョンを `0.2.1` → `0.2.2` に更新する。

- `pyproject.toml`: `version = "0.2.2"`
- `__init__.py`: `__version__ = "0.2.2"`

### T-803-2: `design/tasks.md` にフェーズ 7 を追記
対象ファイル: `design/tasks.md`

フェーズ 6 の後に以下を追記する:

```markdown
## フェーズ 7: 記憶重複防止・統合

> 設計書: [memory-dedup-design.md](./memory-dedup-design.md)

`tasks` ディレクトリにタスク化済み（800〜803）

| タスク | 概要 | 依存 |
|---|---|---|
| 800 | remember 保存前の重複検出ガード | なし |
| 801 | consolidate でのマージ候補検出 | 800 |
| 802 | スキャフォールドへの重複意識の追加 | 800 |
| 803 | バージョンアップと CI 全チェック | 800〜802 |
```

### T-803-3: CI 全チェック実行
800〜802 の変更を含めた全コードに対して CI チェックを実行し、全て pass することを確認する。

```bash
cd ego-mcp
uv sync --extra dev
GEMINI_API_KEY=test-key uv run pytest tests -v
uv run isort --check-only src tests
uv run ruff check src tests
uv run mypy src tests
```

バージョン確認:
```bash
uv run python -c "import ego_mcp; print(ego_mcp.__version__)"
# 出力: 0.2.2
```

## 完了確認
```bash
cd ego-mcp
GEMINI_API_KEY=test-key uv run pytest tests -v
uv run isort --check-only src tests
uv run ruff check src tests
uv run mypy src tests
uv run python -c "import ego_mcp; print(ego_mcp.__version__)"
```
