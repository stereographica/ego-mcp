# 703: feel_desires スキャフォールド改善

## 目的
`SCAFFOLD_FEEL_DESIRES` の `satisfy_desire` への誘導を、行動指示型から認知の型（内的気づき）に改善する。

## 前提
- 702（暗黙の充足）が完了していること（暗黙の充足により実際に欲求間の差が生まれていることが前提）

## 参照
- `design/desire-system-rebalance.md` §C

## タスク

### T-703-1: `SCAFFOLD_FEEL_DESIRES` の変更
対象ファイル: `src/ego_mcp/scaffolds.py`

`SCAFFOLD_FEEL_DESIRES` の最終行を変更する。

旧:
```
After acting on a desire, use satisfy_desire.
```

新:
```
Does any urge feel quieter than before? If something feels settled, acknowledge it with satisfy_desire.
```

他の行（1〜2 行目）は変更しない。

**変更の意図:**
- 旧: 「行動した後にツールを呼べ」（手続き的な行動指示）
- 新: 「欲求が静まった感覚に気づけ」（内的状態の変化への問いかけ）
- `satisfy_desire` への導線は維持しつつ、認知スキャフォールドの設計思想（「行動指示ではなく認知の型を提供する」）に合わせる

### T-703-2: テスト更新
対象ファイル: `tests/test_scaffolds.py`

`SCAFFOLD_FEEL_DESIRES` の内容をアサートしているテストがあれば、新しい文言に更新する。具体的には、旧文言 `"After acting on a desire, use satisfy_desire."` を含むアサーションを新文言に変更する。

## 完了確認
```bash
cd ego-mcp
GEMINI_API_KEY=test-key uv run pytest tests/test_scaffolds.py -v
uv run mypy src/ego_mcp/scaffolds.py
```
