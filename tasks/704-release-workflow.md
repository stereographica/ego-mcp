# 704: バージョニングとリリースワークフローの整備

## 目的
マイグレーションフレームワークの導入に伴い、バージョン更新漏れを防ぐためのリリースワークフローを `CLAUDE.md` に定義する。また、今回の変更を v0.2.0 としてリリースする。

## 前提
- 700〜703 が全て完了していること

## 参照
- `design/desire-system-rebalance.md` §E

## タスク

### T-704-1: バージョン番号の更新
対象ファイル: `ego-mcp/pyproject.toml`, `ego-mcp/src/ego_mcp/__init__.py`

両ファイルのバージョンを `0.1.0` → `0.2.0` に更新する。

- `pyproject.toml`: `version = "0.2.0"`
- `__init__.py`: `__version__ = "0.2.0"`

701 で作成するマイグレーションファイル `0002_desire_rebalance.py` の `TARGET_VERSION` が `"0.2.0"` であることを確認する。

### T-704-2: CLAUDE.md にリリースワークフローを追記
対象ファイル: `CLAUDE.md`（リポジトリルート）

`## ego-mcp リリースワークフロー` セクションを追加する。内容:

```markdown
## ego-mcp リリースワークフロー

ego-mcp のコード変更をリリースする際は以下に従う:

1. `ego-mcp/pyproject.toml` の `version` を更新
2. `ego-mcp/src/ego_mcp/__init__.py` の `__version__` を同じ値に更新
3. マイグレーションファイルがある場合: `TARGET_VERSION` が新バージョンと一致することを確認
4. CI チェックを全て通す
5. マージ後に `git tag v{version}` を付与
```

追記する場所は `## Mandatory CI Gate After Code Changes` セクションの前とする。

### T-704-3: `design/tasks.md` にフェーズ 6 を追記
対象ファイル: `design/tasks.md`

フェーズ 5 の後に以下を追記する:

```markdown
## フェーズ 6: 欲求システム・リバランス

> 設計書: [desire-system-rebalance.md](./desire-system-rebalance.md)

`tasks` ディレクトリにタスク化済み（700〜704）

| タスク | 概要 | 依存 |
|---|---|---|
| 700 | マイグレーションフレームワーク | なし |
| 701 | satisfaction_hours 調整 + マイグレーション | 700 |
| 702 | 暗黙の充足（Implicit Satisfaction） | 701 |
| 703 | feel_desires スキャフォールド改善 | 702 |
| 704 | バージョニングとリリースワークフロー | 700〜703 |
```

依存関係図にも以下を追記する:

```
T-700 (マイグレーション基盤) ─→ T-701 (satisfaction_hours)
                              ─→ T-702 (暗黙の充足)
                              ─→ T-703 (スキャフォールド)
T-700〜703 ─→ T-704 (リリースワークフロー)
```

### T-704-4: CI 全チェック実行
700〜703 の変更を含めた全コードに対して CI チェックを実行し、全て pass することを確認する。

```bash
cd ego-mcp
uv sync --extra dev
GEMINI_API_KEY=test-key uv run pytest tests -v
uv run isort --check-only src tests
uv run ruff check src tests
uv run mypy src tests
```

## 完了確認
```bash
cd ego-mcp
GEMINI_API_KEY=test-key uv run pytest tests -v
uv run isort --check-only src tests
uv run ruff check src tests
uv run mypy src tests
# バージョン確認
uv run python -c "import ego_mcp; print(ego_mcp.__version__)"
# 出力: 0.2.0
```
