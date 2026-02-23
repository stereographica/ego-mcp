# 700: マイグレーションフレームワーク

## 目的
ego-mcp のデータファイル（`desires.json`, `self_model.json` 等）に対する自動マイグレーション基盤を新設する。所定ディレクトリにタスクファイルを配置するだけでサーバー起動時に自動実行される仕組みを作る。

## 前提
- なし（他タスクに依存しない）

## 参照
- `design/desire-system-rebalance.md` §D

## タスク

### T-700-1: マイグレーションモジュールの作成
対象ファイル: `src/ego_mcp/migrations/__init__.py`（新規）

`ego_mcp.migrations` パッケージを作成し、`MigrationRunner` を実装する。

**`run_migrations(data_dir: Path) -> list[str]`:**
1. `data_dir / "migration_state.json"` から適用済みマイグレーション名の一覧を読み込む（ファイルがなければ空リスト）
2. `migrations/` ディレクトリ内の `[0-9][0-9][0-9][0-9]_*.py` にマッチするファイルを発見し、ファイル名順にソートする
3. 各マイグレーションモジュールを `importlib.import_module` で読み込み、`TARGET_VERSION`（str）と `up(data_dir: Path) -> None` を取得する
4. 適用済みリストに含まれないマイグレーションを順番に実行する
5. 実行後、`migration_state.json` の `applied` リストを更新して保存する
6. 適用したマイグレーション名のリストを返す

**`migration_state.json` の形式:**
```json
{
  "applied": [
    "0002_desire_rebalance"
  ]
}
```

**マイグレーションタスクファイルの規約:**
- ファイル名: `NNNN_description.py`（0 埋め 4 桁連番）
- 必須属性: `TARGET_VERSION: str` — このマイグレーションが含まれるリリースバージョン
- 必須関数: `up(data_dir: Path) -> None` — マイグレーション処理本体
- `0001` は予約番号（フレームワーク導入前の状態を表す）。実マイグレーションは `0002` から開始する

**ログ出力:**
- マイグレーション適用時に `logging.info` で `"Applying migration: %s (target: %s)"` を出力
- 全適用後に `"Applied %d migration(s): %s"` を出力

### T-700-2: サーバー起動時のマイグレーション呼び出し
対象ファイル: `src/ego_mcp/server.py`

`init_server()` 内で、`config.data_dir.mkdir(...)` の直後かつコンポーネント初期化（`MemoryStore`, `DesireEngine` 等）の前に `run_migrations(config.data_dir)` を呼び出す。

これにより、各コンポーネントがデータファイルを読む時点ではマイグレーションが完了している。

### T-700-3: マイグレーションのテスト
対象ファイル: `tests/test_migrations.py`（新規）

- マイグレーションタスクファイルが存在する場合に `run_migrations` が `up()` を実行すること
- 適用済みのマイグレーションがスキップされること
- `migration_state.json` が正しく更新されること
- `migration_state.json` が存在しない状態からの初回実行が正常に動作すること
- `TARGET_VERSION` がないファイルがスキップされること（warning ログ出力）

## 完了確認
```bash
cd ego-mcp
GEMINI_API_KEY=test-key uv run pytest tests/test_migrations.py -v
uv run mypy src/ego_mcp/migrations
```
