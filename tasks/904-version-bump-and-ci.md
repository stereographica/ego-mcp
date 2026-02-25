# 904: バージョンアップと CI 全チェック

## 目的
900〜903 の変更を含めてバージョンを v0.2.3 に更新し、CI チェックを全て通す。

## 前提
- 900〜903 が全て完了していること

## 参照
- `design/forget-tool-design.md`（実装スコープ > バージョニング）
- `CLAUDE.md`（ego-mcp リリースワークフロー）

## タスク

### T-904-1: バージョン番号の更新
対象ファイル: `ego-mcp/pyproject.toml`, `ego-mcp/src/ego_mcp/__init__.py`

両ファイルのバージョンを `0.2.2` → `0.2.3` に更新する。

- `pyproject.toml`: `version = "0.2.3"`
- `__init__.py`: `__version__ = "0.2.3"`

### T-904-2: CHANGELOG.md の更新
対象ファイル: `ego-mcp/CHANGELOG.md`

`[0.2.2]` エントリの上に `[0.2.3]` エントリを追加する。以下の内容を含める:

- **Added**: `forget` ツール、`MemoryStore.delete` メソッド、`WorkspaceMemorySync.remove_memory` メソッド
- **Changed**: `consolidate` のマージ候補スキャフォールドに `forget` への導線を追加、`get_episode` で削除済み memory_ids のフィルタを追加

### T-904-3: `design/tasks.md` にフェーズ 8 を追記
対象ファイル: `design/tasks.md`

フェーズ 7 の後に以下を追記する:

```markdown
## フェーズ 8: forget ツール

> 設計書: [forget-tool-design.md](./forget-tool-design.md)

`tasks` ディレクトリにタスク化済み（900〜904）

| タスク | 概要 | 依存 |
|---|---|---|
| 900 | MemoryStore.delete メソッドの追加 | なし |
| 901 | Workspace Sync のエントリ除去 | 900 |
| 902 | forget ツールの追加 | 900, 901 |
| 903 | スキャフォールド改善とドキュメント更新 | 902 |
| 904 | バージョンアップと CI 全チェック | 900〜903 |
```

### T-904-4: CI 全チェック実行
900〜903 の変更を含めた全コードに対して CI チェックを実行し、全て pass することを確認する。

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
# 出力: 0.2.3
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
