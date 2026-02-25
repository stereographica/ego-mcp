# 901: Workspace Sync のエントリ除去

## 目的
`WorkspaceMemorySync` に、記憶の削除時に同期済み Markdown ファイルから該当エントリを除去するメソッドを追加する。

## 前提
- 900（`MemoryStore.delete`）が完了していること
- `WorkspaceMemorySync` が動作していること
- 同期済みエントリが `[id:{memory_id}]` マーカーで識別可能であること

## 参照
- `design/forget-tool-design.md` §B

## タスク

### T-901-1: `_remove_lines_with_marker` ヘルパーの実装
対象ファイル: `ego-mcp/src/ego_mcp/workspace_sync.py`

`WorkspaceMemorySync` クラスに以下のプライベートメソッドを追加する:

```python
def _remove_lines_with_marker(self, path: Path, marker: str) -> bool:
```

- 指定パスのファイルを読み込み、`marker` を含む行を除去して書き戻す
- ファイルが存在しない場合は `False` を返す
- マーカーが含まれる行がない場合は `False` を返す（ファイル書き込みもしない）
- 1 行以上除去した場合は `True` を返す

### T-901-2: `remove_memory` メソッドの実装
対象ファイル: `ego-mcp/src/ego_mcp/workspace_sync.py`

`WorkspaceMemorySync` クラスに以下のメソッドを追加する:

```python
def remove_memory(self, memory_id: str) -> bool:
```

- `[id:{memory_id}]` をマーカーとして構成する
- `self._memory_dir` 配下の daily log ファイル（`????-??-??.md` パターン）を走査し、`_remove_lines_with_marker` でマーカーを含む行を除去する
- `self._curated_memory`（`MEMORY.md`）に対しても同様に除去する
- `latest monologue`（`memory/inner-monologue-latest.md`）は対象外（上書き設計のため）
- いずれかのファイルが変更された場合に `True` を返す

### T-901-3: テスト
対象ファイル: `ego-mcp/tests/test_workspace_sync.py`

以下のテストケースを追加する:

- daily log にマーカー付きエントリがある場合: `remove_memory` で該当行が除去されること
- curated memory にマーカー付きエントリがある場合: `remove_memory` で該当行が除去されること
- マーカーが存在しない場合: ファイル内容が変更されないこと、`False` が返ること
- ファイルが存在しない場合: エラーにならず `False` が返ること
- 複数の daily log ファイルにまたがる場合: 全ファイルから除去されること

## 完了確認
```bash
cd ego-mcp
GEMINI_API_KEY=test-key uv run pytest tests/test_workspace_sync.py -k "remove" -v
uv run mypy src/ego_mcp/workspace_sync.py
```
