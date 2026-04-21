# Migration Guide: v0.6.x to v1.0.0

## Breaking Changes

### Tool Surface Changes

| Old Name | New Name | Notes |
|---|---|---|
| `feel_desires` | `attune` | Unified emotional awareness (desires + emotion + interests) |
| `am_i_being_genuine` | `pause` | Same functionality, shorter name |
| `satisfy_desire` | (removed) | Desire satisfaction is now handled automatically via `remember` |
| `emotion_trend` | (removed) | Emotional layer analysis is now part of `attune` |
| — | `configure_desires` | New backend tool for viewing/editing desire settings |

If your prompts or workflows reference the old tool names, update them to use the new names.

### Desire Catalog Schema (v1 to v2)

The desire catalog (`settings/desires.json`) schema has changed:

- **Sentence templates**: `{medium, high}` replaced by `{rising, steady, settling}`
- **New field**: `satisfaction_signals` (list of strings, optional)
- **Version**: `1` updated to `2`
- **Implicit satisfaction references**: `emotion_trend` and `feel_desires` renamed to `attune`

### EMA Baseline Tracking

Desire state (`desire_state.json`) now includes two new fields per desire:
- `ema_level` (float): Exponential moving average of desire level (default: 0.5)
- `ema_updated_at` (string): ISO timestamp of last EMA update

These are populated automatically; no manual action is needed.

## Automatic Migration

Migration `0007_desire_catalog_v2` runs automatically on startup and handles:

1. Converting sentence templates: `medium` to `steady`, `high` to `rising`
2. Adding empty `settling` placeholder for each desire
3. Adding default empty `satisfaction_signals` list
4. Renaming `emotion_trend`/`feel_desires` references to `attune` in `implicit_satisfaction` and `implicit_rules`
5. Updating `version` to `2`

A backup is created at `settings/desires.pre_0007_catalog_v2.json` before any changes.

## Custom `desires.json` Users

If you have customized `settings/desires.json`:

1. **After migration**: The `settling` sentence for each desire will be an empty string. You should fill these in with appropriate text using:
   ```
   configure_desires(action="set_sentence", desire_id="curiosity", direction="settling", sentence="The itch to know has settled for now.")
   ```

2. **Satisfaction signals** are optional but recommended for future auto-satisfaction inference:
   ```
   configure_desires(action="set_signals", desire_id="curiosity", signals=["finding an answer", "exploring something unknown"])
   ```

3. **Check incomplete configuration**:
   ```
   configure_desires(action="check")
   ```
   This reports any desires missing `settling` sentences or `satisfaction_signals`.

## New Features

### `attune` Tool

Combines the functionality of `feel_desires` and `emotion_trend` into a single unified view:
- Emotional texture (recent emotional events)
- Desire currents (3-direction: rising/steady/settling, relative to EMA baseline)
- Emergent desire pull
- Current interests (derived from recent memories and notions)
- Body sense (time phase)

### `configure_desires` Tool

Backend tool for viewing and editing desire settings at runtime:
- `check`: List incomplete configuration
- `show`: Display desire settings (one or all)
- `set_sentence`: Set a sentence template for a desire direction
- `set_signals`: Set satisfaction signals for a desire

### 3-Direction Desire System

Desires now express in three directions relative to their EMA baseline:
- **rising**: Level significantly above baseline (`level > ema + 0.15`)
- **steady**: Level near baseline (`|level - ema| <= 0.15`)
- **settling**: Level significantly below baseline (`level < ema - 0.15`)

### Current Interest Derivation

A computed view that synthesizes interests from recent memories, notions, and emergent desires. Shown in the `attune` output.
