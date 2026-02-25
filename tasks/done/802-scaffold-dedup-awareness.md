# 802: スキャフォールドへの重複意識の追加

## 目的
`SCAFFOLD_INTROSPECT` の `remember` への誘導部分に、記憶の新規性を自己評価させるニュアンスを追加する。保存前ガード（800）と相補的に機能し、エージェントの認知品質を高める。

## 前提
- 800（remember 保存前の重複検出ガード）が完了していること

## 参照
- `design/memory-dedup-design.md` §C

## タスク

### T-802-1: `SCAFFOLD_INTROSPECT` の変更
対象ファイル: `ego-mcp/src/ego_mcp/scaffolds.py`

2 行目を以下のように変更する:

**現行:**
```
Save with remember (category: introspection).
```

**変更後:**
```
If this is a genuinely new insight, save with remember (category: introspection).
```

他の行は変更しない。

### T-802-2: テスト
対象ファイル: `ego-mcp/tests/test_scaffolds.py`

`SCAFFOLD_INTROSPECT` に `"genuinely new insight"` が含まれることを確認するテストを追加（または既存テストを更新）する。

## 完了確認
```bash
cd ego-mcp
GEMINI_API_KEY=test-key uv run pytest tests/test_scaffolds.py -v
uv run mypy src/ego_mcp/scaffolds.py
```
