# 201: 自己モデル拡張（Phase 2）

## 目的
`introspect` の自己理解セクションを実データ化するため、自己モデルの保存・更新・問い管理を実装する。

## 前提
- `introspect` が scaffold 付きで返ること
- `MemoryStore.list_recent()` が利用可能であること

## 参照
- `design/tasks.md` の T-201
- `design/tool-design.md` の `introspect`

## タスク

### T-201-1: `src/ego_mcp/self_model.py` の実装
- [ ] `SelfModelStore.__init__(path: Path)` を実装（JSON 永続化）
- [ ] `SelfModelStore.get()` を実装
- [ ] `SelfModelStore.update(patch: dict[str, Any])` を実装（部分更新）
- [ ] `SelfModelStore.add_question(question: str)` を実装
- [ ] `SelfModelStore.resolve_question(question_id: str)` を実装
- [ ] JSON 破損時フォールバックを実装

### T-201-2: `introspect` を自己モデルへ接続
- [ ] `server.py` の `introspect` で `SelfModelStore` を参照
- [ ] 未解決の問いを `introspect` のデータ部へ表示
- [ ] 最近記憶から簡易傾向サマリを追加
- [ ] 既存 scaffold（`SCAFFOLD_INTROSPECT`）を維持

## テスト
- [ ] `tests/test_self_model.py` を作成
  - get/update/add_question/resolve_question
  - 永続化確認
- [ ] `tests/test_integration.py` に `introspect` 反映ケースを追加

## 完了確認
```bash
cd ego-mcp
uv run pytest tests/test_self_model.py -v
uv run pytest tests/test_integration.py -k introspect -v
```

