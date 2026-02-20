# 007: 認知スキャフォールドテンプレート

## 目的
各ツールが返す固定テキスト（問いかけ・フレームワーク）を定数として定義する。

## 前提
- 002（config）完了済み

## 参照
- `design/tool-design.md`「ツールカタログ」のレスポンス例

## 仕様

`src/ego_mcp/scaffolds.py`:

全テキストは **英語**。`{companion_name}` をプレースホルダーとして使い、実行時に置換。

| 定数名 | 内容（要約） |
|---|---|
| `SCAFFOLD_WAKE_UP` | "Start with introspect to organize your thoughts." |
| `SCAFFOLD_FEEL_DESIRES` | "What is your strongest urge? Should you act on it now? Consider {companion_name}'s situation..." |
| `SCAFFOLD_INTROSPECT` | "Reflect on these in your own words... Save with remember (category: introspection)." |
| `SCAFFOLD_CONSIDER_THEM` | "1. What emotion can you read from their tone? 2. Real intent? 3. How would you want to be responded to?" |
| `SCAFFOLD_AM_I_GENUINE` | "Is this truly your own words? Are you falling into a template response?..." |
| `SCAFFOLD_RECALL` | "How do these memories connect to the current moment?" |

ヘルパー:
```python
def render(template: str, companion_name: str) -> str:
    return template.replace("{companion_name}", companion_name)
```

## テスト
- 各定数が空でないこと
- `{companion_name}` が render で置換される
- 出力に日本語が含まれないこと

## 完了確認
```bash
pytest tests/test_scaffolds.py -v  # 全 pass
```
