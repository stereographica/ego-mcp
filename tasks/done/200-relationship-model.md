# 200: 関係性モデル拡張（Phase 2）

## 目的
`consider_them` をスタブから実データ駆動に置き換えるため、関係性モデルの保存・更新・参照機能を実装する。

## 前提
- 既存の `update_relationship` ツールが動作していること
- `MemoryStore` で `conversation` カテゴリの記憶を検索できること

## 参照
- `design/tasks.md` の T-200
- `design/tool-design.md` の `consider_them`

## タスク

### T-200-1: `src/ego_mcp/relationship.py` の実装
- [ ] `RelationshipStore.__init__(path: Path)` を実装し、JSON ファイル永続化を有効化
- [ ] `RelationshipStore.get(person_id: str)` を実装
- [ ] `RelationshipStore.update(person_id: str, patch: dict[str, Any])` を実装（部分更新）
- [ ] `RelationshipStore.add_interaction(person_id: str, timestamp: str, tone: str)` を実装
- [ ] `RelationshipStore.add_shared_episode(person_id: str, episode_id: str)` を実装
- [ ] JSON 破損時は空データへフォールバック

### T-200-2: `consider_them` を関係性モデルへ接続
- [ ] `server.py` の `consider_them` で `RelationshipStore` を参照
- [ ] `conversation` 記憶から頻度・トーンを集計する補助関数を追加
- [ ] レスポンスに以下を含める
  - 関係性の要約
  - 最近の対話傾向（頻度・トーン）
  - 既存 scaffold（`SCAFFOLD_CONSIDER_THEM`）

## テスト
- [ ] `tests/test_relationship.py` を作成
  - CRUD（get/update/add_interaction/add_shared_episode）
  - JSON 永続化確認
- [ ] `tests/test_integration.py` に `consider_them` 反映ケースを追加

## 完了確認
```bash
cd ego-mcp
uv run pytest tests/test_relationship.py -v
uv run pytest tests/test_integration.py -k consider_them -v
```

