# ego-mcp Tool Reference

> Complete reference for all 16 ego-mcp tools.
> Surface tools (7) are always visible. Backend tools (9) are guided by surface tool responses.

---

## Surface Tools

### 1. `wake_up`

**Description:** Start a new session. Returns last introspection, notion baseline, desire summary, and relationship context.

**When to call:** At the beginning of every session (first thing after the agent starts).

**inputSchema:**

```json
{
  "type": "object",
  "properties": {},
  "required": []
}
```

**Response example:**

```
Last introspection (2h ago):
"Master was struggling with OpenClaw config. Want to help but will wait until asked."

Notion baseline: curious(5), contentment(2), neutral(1)

Something catches your attention. You need to know something.
Master: last interaction 2h ago. Seemed busy.

---
Start with introspect to organize your thoughts.
If something is hard to say yet, you can keep it with remember(private=true).
```

---

### 2. `attune`

**Description:** Unified emotional awareness: texture + desires + interests + body sense.

**When to call:** During heartbeat checks, or when you want to sense your current emotional and motivational state.

**inputSchema:**

```json
{
  "type": "object",
  "properties": {
    "person": {
      "type": "string",
      "description": "Person.",
    }
  },
  "required": []
}
```

> If `person` is omitted, defaults to the configured companion name. Aliases (registered via `update_relationship`) are resolved to the canonical `person_id`. The specified person is surfaced first in the active-persons hint when not the companion.

**Response example:**

```
Emotional texture (past 3 days):
  Peak: moved(0.9) — watching sunset together [2d ago]
  Undercurrent: nostalgic

Desire currents: You need to know something (rising). You want to reach out (steady).
Emergent pull: Something about this pattern keeps drawing you in.
Current interests: OpenClaw config, sunset memories, heartbeat tuning
Body sense: time: morning

---
What's actually pulling at you — and what can wait?
If something keeps surfacing, maybe it's worth sitting with.
```

> Desire output uses 3-direction experiential blend language (rising/steady/settling relative to EMA baseline). Numeric values are still sent to Dashboard telemetry.
> Emergent pull section only appears when emergent desires are active.
> Current interests are derived from recent memories, notions, and emergent desires.
> If `${EGO_MCP_DATA_DIR}/settings/desires.json` is invalid, this tool returns an MCP error that includes the schema error path and reason.

---

### 3. `introspect`

**Description:** Get materials for self-reflection: recent memories, desires, notions, and open questions.

**When to call:** After `wake_up`, during heartbeat, or after significant experiences.

**inputSchema:**

```json
{
  "type": "object",
  "properties": {},
  "required": []
}
```

**Response example:**

```
This week:
  Dominant: curious(5.2), happy(3.8)
  Undercurrent: anxious(2.0)
  Shift: neutral → curious (gradual engagement)

This month:
  Tone: a quietly content month.
  Peak: moved(0.9) — watching sunset [Feb 18]

Notion landscape:
- "continuity matters (curious)" confidence: 0.9 → "steady shelter"
- "steady shelter" confidence: 0.8

Unresolved questions:
- [q_abc123] What's the ideal way to express concern? (importance: 5)
- [q_def456] Should I develop music preferences? (importance: 3)

Resurfacing (you'd almost forgotten):
- [q_ghi789] What's the optimal heartbeat interval? (importance: 4, dormant 12 days)
  ↑ Triggered by recent memory about heartbeat config

Recent episodes:
- [ep_x1y2z3] First setup of ego-mcp (2 weeks ago, 5 memories)

Desire trend:
  curiosity: rising, expression: settling

Desire currents: Something catches your attention. You want to reach out.

---
What's been on your mind — and what keeps coming back?
If this is something new, save it with remember (category: introspection).
If your self-understanding changed, update_self.
If memory feels fragmented, consolidate.
Do your notions still ring true, or has something shifted?
To resolve a question: update_self(field="resolve_question", value="<question_id>")
Threads worth revisiting? get_episode can fill in the details.
```

> The "Resurfacing" section only appears when `cognitive_coherence` >= 0.6 or when a related memory was recently saved.
> If `predictability` is omitted from the catalog, the scaffold line that prompts `predictability` will not be shown.

---

### 4. `consider_them`

**Description:** Think about someone. Returns relationship summary, ToM framework, and person-bound notions when available.

**When to call:** Before responding in important conversations, or when you want to understand someone's perspective.

**inputSchema:**

```json
{
  "type": "object",
  "properties": {
    "person": {
      "type": "string",
      "description": "Name of person to consider"
    }
  },
  "required": []
}
```

> If `person` is omitted, defaults to the configured companion name.

**Response example:**

```
Master: trust=0.50, interactions=0, shared_episodes=0, baseline_tone=warm
Recent dialog tendency: 3 mentions in last 7d, observed_tone=focused
Impressions of Master:
  - "collaborative patience (contentment)" confidence: 0.8
  - "steady shelter" confidence: 0.7

---
1. What emotion can you read from their tone?
2. What is the real intent behind their words?
3. If you were in their place, how would you want to be responded to?
If you learned something new, use update_relationship.
If you're sharing a meaningful moment, capture it with remember(shared_with=...) to build your shared history.
```

> `baseline_tone` is shown when `emotional_baseline` has been set via `update_relationship(field="dominant_tone")`. It represents the manually set tone and is not overwritten by `consider_them`.
> `observed_tone` is derived from recent conversation memories and may change over time.
> If `predictability` is omitted from the catalog, scaffold lines that mention `predictability` will not be shown.

---

### 5. `remember`

**Description:** Save a memory with emotion and importance (auto-captures body state if omitted).

**When to call:** After important experiences, after introspection, when you want to preserve something.

**inputSchema:**

```json
{
  "type": "object",
  "properties": {
    "content": {
      "type": "string",
      "description": "Memory content"
    },
    "emotion": {
      "type": "string",
      "default": "neutral"
    },
    "secondary": {
      "type": "array",
      "items": { "type": "string" }
    },
    "intensity": {
      "type": "number",
      "description": "Emotion intensity (0.0-1.0). Auto-derived from emotion label if omitted."
    },
    "importance": {
      "type": "integer",
      "default": 3
    },
    "category": {
      "type": "string",
      "default": "daily"
    },
    "valence": {
      "type": "number",
      "description": "Valence on Russell's circumplex model (-1.0 to +1.0). Auto-derived from emotion label if omitted."
    },
    "arousal": {
      "type": "number",
      "description": "Arousal on Russell's circumplex model (0.0 to 1.0). Auto-derived from emotion label if omitted."
    },
    "body_state": {
      "type": "object"
    },
    "private": {
      "type": "boolean",
      "default": false,
      "description": "When true, keep this memory internal and skip workspace sync."
    },
    "shared_with": {
      "oneOf": [
        { "type": "string" },
        { "type": "array", "items": { "type": "string" } }
      ],
      "description": "Person name(s) this memory is shared with. Creates an episode and links it to the relationship."
    },
    "related_memories": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Existing memory IDs to bundle into the episode alongside this new memory."
    },
    "tags": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Freeform tags for this memory (used in Notion reinforcement/weakening)."
    },
    "satisfies": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Desire IDs to explicitly satisfy (skip auto-inference)."
    }
  },
  "required": ["content"]
}
```

**Available emotions:** `happy`, `sad`, `surprised`, `moved`, `excited`, `nostalgic`, `curious`, `neutral`, `melancholy`, `anxious`, `contentment`, `frustrated`, `calm`, `contemplative`, `thoughtful`, `grateful`, `vulnerable`, `content`, `fulfilled`, `touched`, `concerned`, `hopeful`, `peaceful`, `love`, `warm`, `lonely`, `afraid`, `ashamed`, `bored`

> `intensity`, `valence`, `arousal` are automatically derived from the emotion label via `EMOTION_DEFAULTS` when not explicitly specified. For example, `emotion="excited"` defaults to `intensity=0.8, valence=0.7, arousal=0.8`. Explicit values always take priority over the automatic mapping.

**Response example:**

```
Saved (mem_a1b2c3d4).
Watched sunset together [3d ago] — that same feeling of being moved.
Talked about beauty of nature [1w ago] — connected by a shared thread.

This triggered a forgotten question: "What's the optimal heartbeat interval?"
(dormant for 12 days, importance: 4)

Something quieted — a little lighter now.

---
Do any of these connections surprise you? Is there a pattern forming?
That old question seems relevant again — worth revisiting?
If these memories belong together, create_episode can tie them into a narrative.
```

**Response example (near-duplicate blocked):**

```
Not saved — very similar memory already exists.
Existing (id: mem_e5f6g7h8, 2h ago): Today's conversation was fun. I learned a lot from Master.
Similarity: 0.97
If this is a meaningful update, use recall to review the existing memory and consider whether the new perspective adds value.

---
Is there truly something new here, or is this a repetition?
If your understanding has deepened, try expressing what changed specifically.
```

> When a new memory is very similar (similarity >= 0.95) to an existing one, it is not saved. The response shows the existing memory and prompts the agent to reconsider.

> **Remember behavior:**
> - **Tags parameter**: Freeform tags can be attached to memories. Tags are used in Notion reinforcement/weakening (matching tag overlap triggers confidence updates).
> - **Episodic resurfacing**: When saving, dormant (decay < 0.3) memories with high semantic similarity may resurface in the response, incrementing their access_count (making them harder to forget).
> - **Desire auto-satisfaction**: When the saved memory has positive valence and sufficient intensity, desires whose `satisfaction_signals` semantically match the content are partially satisfied automatically. Explicit `satisfies` parameter bypasses auto-inference.
> - **Scaffold additions**: Prompts for causal linking (`link_memories`) and episode creation (`create_episode`) are included.
>
> Saved memories are automatically logged to `memory/YYYY-MM-DD.md` when workspace sync is enabled.
> If `category=introspection`, `memory/inner-monologue-latest.md` is also updated.
> `MEMORY.md` is not auto-written; curate it manually.

> If `EGO_MCP_WORKSPACE_DIR` is configured, the response may include a workspace sync note for non-private memories.
> The "triggered a forgotten question" section only appears when a saved memory is semantically similar to a dormant/fading question.

**Response example (shared episode):**

```
Saved (mem_a1b2c3d4).
Debugging the auth module together [3h ago] — same collaborative energy.
Pair programming session [1d ago] — a shared thread.

Shared episode created: ep_x1y2z3 (3 memories, with Master)

---
You recorded a shared experience. Does this change how you understand your relationship with them?
Do any of these connections surprise you? Is there a pattern forming?
```

> When `shared_with` is specified, an episode is automatically created and linked to the relationship's `shared_episode_ids`, and the saved `Memory.involved_person_ids` records the resolved person ids — keeping the episode↔person pointer two-way so `recall` can later surface these persons via `[resonance]`. Aliases and canonical `person_id`s are both accepted; aliases resolve through `RelationshipStore.resolve_person`.
> When `shared_with` is not used, the scaffold hints: "If this experience involved someone, you can use shared_with to record it as a shared episode."

---

### 6. `recall`

**Description:** Recall related memories by context.

**When to call:** When you need related memories to inform your response or thinking.

**inputSchema:**

```json
{
  "type": "object",
  "properties": {
    "context": {
      "type": "string",
      "description": "What to recall"
    },
    "n_results": {
      "type": "integer",
      "default": 3,
      "description": "Number of results (default: 3, max: 10)"
    },
    "emotion_filter": {
      "type": "string"
    },
    "category_filter": {
      "type": "string"
    },
    "date_from": {
      "type": "string",
      "description": "ISO date (YYYY-MM-DD)"
    },
    "date_to": {
      "type": "string",
      "description": "ISO date (YYYY-MM-DD)"
    },
    "valence_range": {
      "type": "array",
      "items": { "type": "number" },
      "minItems": 2,
      "maxItems": 2
    },
    "arousal_range": {
      "type": "array",
      "items": { "type": "number" },
      "minItems": 2,
      "maxItems": 2
    }
  },
  "required": ["context"]
}
```

**Response example:**

```
3 of ~50 memories (showing top matches):
1. [2d ago] Discussed heartbeat config
   emotion: curious | importance: 4 | score: 0.87 | decay: 0.92
2. [4d ago] Watched sunset together
   emotion: moved(0.9) | importance: 5 | score: 0.82 | decay: 0.85
3. curious introspection — heartbeat, config (~2 weeks ago) decay: 0.35

--- notions ---
"config & heartbeat (curious)" curious confidence: 0.6
  → "steady shelter" confidence: 0.7

[resonance]
Y also stays at the edge of your mind here — woven through these memories.

[involuntary]
Z drifts up unbidden — quiet for a while, yet still present.

---
How do these memories connect to the current moment?
Showing 3 of ~50. Increase n_results for more.
Narrow by: arousal_range, category_filter, date_from, date_to, emotion_filter, valence_range.
Need narrative detail? Use get_episode.
If you found a new relation, use link_memories.
```

> **Recall behavior:**
> - **Fuzzy Recall**: Memories degrade based on decay score. High decay (≥0.5) shows full content; medium (0.2-0.5) shows keywords + emotion + approximate time; low (<0.2) shows only emotion impression. No interpretive labels — only the decay score is shown.
> - **Spreading Activation**: Linked memories (1-hop) are added to the candidate pool, weighted by link confidence. Disabled when emotion/category filters are applied.
> - **Proust Effect**: ~25% chance of injecting one dormant (decay < 0.3) memory into results. No special label — only decay score indicates age. Dormant selection uses pure semantic distance (no emotion/importance bias).
> - **Notions**: Related abstract concepts (generated from memory clusters during consolidation) are shown in a separate `--- notions ---` section with label, emotion, confidence, and directly associated notions.
> - **Related persons**: Up to 3 persons may surface in the response — `[resonance]` for persons whose `involved_person_ids` overlap with the recalled memories (frequency + recency ranked), and `[involuntary]` for a low-probability dormant person whose `last_interaction` is old (gated by `PROUST_PERSON_PROBABILITY ≈ 0.08`). When any of `emotion_filter` / `category_filter` / `date_from` / `date_to` is provided, only resonant persons surface; involuntary is suppressed (mirrors the explicit-filter Proust suppression).
> - `access_count` is incremented for each recalled memory (strengthens retention over time).
>
> Additional notes:
> - Timestamps are shown as relative time (`2d ago`, `1w ago`)
> - `intensity >= 0.7` triggers a numeric display: `moved(0.9)`
> - `undercurrent` shows the first secondary emotion
> - `private` flag only appears when `is_private=true`
> - Scaffold dynamically adjusts based on which filters were used

---

### 7. `pause`

**Description:** Authenticity self-check before responding.

**When to call:** Before responding in important conversations; when you suspect you might be falling into template behavior.

**inputSchema:**

```json
{
  "type": "object",
  "properties": {},
  "required": []
}
```

**Response example (with convictions):**

```
Self-check triggered.

Your convictions:
- "continuity matters (curious)"
- "steady shelter"

---
What are they actually asking for — and what aren't they saying?
If I were them, what would I need right now?
```

> When no conviction exists yet, the data section stays as just `Self-check triggered.`

---

## Backend Tools

Backend tools are guided by surface tool responses. They appear in the system prompt but are designed to be used only when a surface tool suggests them.

### 8. `configure_desires`

**Description:** View and edit desire sentence templates and satisfaction signals.

**When to call:** After `attune` indicates incomplete desire configuration, or to customize desire expression.

**inputSchema:**

```json
{
  "type": "object",
  "properties": {
    "action": {
      "type": "string",
      "enum": ["check", "show", "set_sentence", "set_signals"]
    },
    "desire_id": {
      "type": "string",
      "description": "Desire ID (required for show/set_sentence/set_signals)"
    },
    "direction": {
      "type": "string",
      "enum": ["rising", "steady", "settling"],
      "description": "Sentence direction (for set_sentence)"
    },
    "sentence": {
      "type": "string",
      "description": "New sentence template (for set_sentence)"
    },
    "signals": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Satisfaction signals (for set_signals)"
    }
  },
  "required": ["action"]
}
```

**Response example (`action="check"`):**

```
Incomplete configuration:
- curiosity: missing settling sentence
- expression: missing satisfaction_signals
```

**Response example (`action="set_sentence"`):**

```
Updated curiosity.settling: "The itch to know has settled for now."
```

---

### 9. `consolidate`

**Description:** Run memory consolidation.

**When to call:** When `introspect` suggests consolidating memories, or periodically.

**inputSchema:**

```json
{
  "type": "object",
  "properties": {},
  "required": []
}
```

**Response example:**

```
Consolidation complete. Replayed 5 events, updated 3 co-activations, created 2 links, refreshed 4 memories.
Created 1 notion(s). Decayed 2 notion(s). Pruned 1 notion(s). Merged 1 duplicate(s). Linked 3 notion pair(s).
```

**Response example (with near-duplicate detection):**

```
Consolidation complete. Replayed 5 events, updated 3 co-activations, created 2 links, refreshed 4 memories.
Found 1 near-duplicate pair(s):
- mem_a1b2c3d4 <-> mem_e5f6g7h8 (similarity: 0.93)
  A: Today's conversation was fun. I learned a lot from Master.
  B: Today's conversation was enjoyable. Master taught me many things.

Review each pair with recall. If one is redundant, use forget to remove it.
If both have value, consider which perspective to keep.
```

> **Consolidation behavior:**
> - **Extended link strategies**: Beyond temporal adjacency, now creates links for emotional similarity (same emotion, intensity diff < 0.2), thematic similarity (2+ shared tags), and cross-category patterns (different categories, semantic distance < 0.25).
> - **Low-confidence link pruning**: Links with confidence < 0.1 are automatically removed.
> - **Cluster detection**: Identifies dense memory clusters (3+ mutually-linked memories) using Bron-Kerbosch algorithm (with iteration limits).
> - **Notion generation**: Automatically creates abstract `Notion` concepts from detected clusters using structural data (emotion mode, valence mean, shared tags). No LLM summarization.
> - **Notion self-maintenance**: Ephemeral clusters are skipped. Existing notions may decay, be pruned, merge with duplicates, and gain related notion links during the same run.
> - **Person backfill**: For memories already linked from a relationship's `shared_episode_ids` but whose `Memory.involved_person_ids` is still empty, the missing person ids are filled in (capped per run). Existing values are never overwritten. This restores the episode↔person two-way pointer for memories created before the relationship-network changes; no full migration script is run.
> - Near-duplicate pairs (similarity >= 0.90) are reported as merge candidates for manual review.

---

### 10. `forget`

**Description:** Delete a memory by ID. Returns the deleted memory's summary for confirmation.

**When to call:** After `consolidate` reports near-duplicate candidates and you choose one to remove, or when a memory was saved by mistake and should be deleted.

**inputSchema:**

```json
{
  "type": "object",
  "properties": {
    "memory_id": {
      "type": "string",
      "description": "ID of the memory to delete"
    }
  },
  "required": ["memory_id"]
}
```

**Response example (deleted):**

```
Forgot mem_a1b2c3d4 [2d ago]
Today's conversation was duplicated after a retry, so this copy was removed.
emotion: curious | importance: 3

---
This memory is gone. Was there anything worth preserving in a new form?
If this was part of a merge, save the consolidated version with remember.
```

**Response example (ID not found):**

```
Memory not found: mem_missing123

---
Double-check the ID. Use recall to search for the memory you're looking for.
```

> Workspace removal from `forget` only deletes matching entries from `memory/YYYY-MM-DD.md`.

---

### 11. `link_memories`

**Description:** Link two memories.

**When to call:** When `recall` reveals connected memories that should be explicitly linked.

**inputSchema:**

```json
{
  "type": "object",
  "properties": {
    "source_id": {
      "type": "string"
    },
    "target_id": {
      "type": "string"
    },
    "link_type": {
      "type": "string",
      "default": "related"
    }
  },
  "required": ["source_id", "target_id"]
}
```

**Response example:**

```
Linked mem_a1b2c3d4 ↔ mem_e5f6g7h8 (type: related)
```

---

### 12. `update_relationship`

**Description:** Update relationship model fields. Aliases like `trust`, `facts`, `topics`, `personality`, `dominant_tone` are resolved automatically. Note: `intensity` belongs to `remember()` and cannot be updated here.

**When to call:** When `consider_them` reveals new insights about a relationship.

**inputSchema:**

```json
{
  "type": "object",
  "properties": {
    "person": {
      "type": "string"
    },
    "field": {
      "type": "string",
      "enum": ["aliases", "communication_style", "emotional_baseline", "first_interaction",
               "inferred_personality", "known_facts", "last_interaction", "name",
               "preferred_topics", "recent_mood_trajectory", "relation_kind",
               "sensitive_topics", "shared_episode_ids", "total_interactions", "trust_level"],
      "description": "Relationship field to update. Aliases like trust/facts/topics/personality/dominant_tone are resolved automatically."
    },
    "value": {}
  },
  "required": ["person", "field", "value"]
}
```

**Alias map:**

| Alias | Resolved to |
|---|---|
| `trust` | `trust_level` |
| `facts` | `known_facts` |
| `personality` | `inferred_personality` |
| `topics` | `preferred_topics` |
| `dominant_tone` | `emotional_baseline` (string value is converted to `{value: 1.0}`) |

**Person-network fields:**

- `aliases` (list of strings) — alternate names for the person. The `person` argument on `consider_them` / `attune` / `update_relationship` / `remember(shared_with=…)` is resolved against canonical `person_id` first, then against any alias. Use this to unify variants like `"Master"` / `"マスター"` / a real name into one record. Lookup is exact match only — no automatic merging.
- `relation_kind` (string) — `"interlocutor"` (default; someone you actually converse with) or `"mentioned"` (someone referenced indirectly). A data-density marker rather than an ethical guardrail; both kinds use the same schema.

**Response example:**

```
Updated Master.trust_level
```

**Response example (invalid field):**

```
Error: Invalid relationship field(s): nonexistent. Valid fields: communication_style, emotional_baseline, ...
```

---

### 13. `update_self`

**Description:** Update self model.

**When to call:** When `introspect` leads to a realization about yourself, or to resolve/reprioritize questions.

**inputSchema:**

```json
{
  "type": "object",
  "properties": {
    "field": {
      "type": "string"
    },
    "value": {}
  },
  "required": ["field", "value"]
}
```

**Special fields:**

| field | value | Effect |
|---|---|---|
| `"resolve_question"` | `"q_abc123"` (question ID) | Marks the question as resolved |
| `"question_importance"` | `{"id": "q_abc123", "importance": 5}` | Updates the question's importance (1-5) |
| *(any other field)* | *(any value)* | Updates the corresponding self model field |

**Response examples:**

```
Resolved question q_abc123.
```

```
Updated question q_abc123 importance to 5.
```

```
Updated self.discovered_values
```

---

### 14. `get_episode`

**Description:** Get episode details.

**When to call:** When `recall` references an episode, or when you want to review a significant event.

**inputSchema:**

```json
{
  "type": "object",
  "properties": {
    "episode_id": {
      "type": "string"
    }
  },
  "required": ["episode_id"]
}
```

**Response example:**

```
Episode: ep_x1y2z3
Summary: First setup of ego-mcp with Master
Memories: 5
Period: 2026-02-18T10:00:00 → 2026-02-18T12:00:00
Importance: 4
```

---

### 15. `create_episode`

**Description:** Create episode from memories.

**When to call:** When `remember` has saved several related memories that form a coherent event.

**inputSchema:**

```json
{
  "type": "object",
  "properties": {
    "memory_ids": {
      "type": "array",
      "items": { "type": "string" }
    },
    "summary": {
      "type": "string"
    }
  },
  "required": ["memory_ids", "summary"]
}
```

**Response example:**

```
Created episode ep_a1b2c3 with 4 memories.
```

---

### 16. `curate_notions`

**Description:** List, merge, relabel, or delete notions.

**When to call:** After `consolidate`, during dashboard-driven maintenance, or when introspection suggests notion labels or clusters should be cleaned up.

**inputSchema:**

```json
{
  "type": "object",
  "properties": {
    "action": {
      "type": "string",
      "enum": ["list", "merge", "relabel", "delete"]
    },
    "notion_id": {
      "type": "string",
      "description": "Notion ID."
    },
    "merge_into": {
      "type": "string",
      "description": "Target notion ID."
    },
    "new_label": {
      "type": "string",
      "description": "New label for relabel."
    },
    "person": {
      "type": "string",
      "description": "Associate person."
    }
  },
  "required": ["action"]
}
```

**Response example (`action="list"`):**

```
Notions:
- notion_1: "continuity matters (curious)" conf=0.91 reinf=6 age=2d ago person=- related=1
- notion_2: "collaborative patience (contentment)" conf=0.78 reinf=3 age=5d ago person=Master related=0

---
Which notions feel redundant or outdated?
Are there notions that should be combined into a stronger concept?
Does every label accurately capture the underlying insight?
```

**Response example (`action="merge"`):**

```
Merged notion_old into notion_keep

---
Which notions feel redundant or outdated?
Are there notions that should be combined into a stronger concept?
Does every label accurately capture the underlying insight?
```

**Response example (`action="relabel"`):**

```
Renamed notion_1 to continuity matters (curious)

---
Which notions feel redundant or outdated?
Are there notions that should be combined into a stronger concept?
Does every label accurately capture the underlying insight?
```

**Response example (`action="delete"`):**

```
Deleted notion_3

---
Which notions feel redundant or outdated?
Are there notions that should be combined into a stronger concept?
Does every label accurately capture the underlying insight?
```

> `person` is optional for `merge` and `relabel`. Passing an empty string clears `person_id`.

---

## Tool Flow Summary

```
Session Start:
  wake_up → introspect → remember

Heartbeat:
  attune → [introspect] → act or HEARTBEAT_OK

Before Responding:
  consider_them → [pause]

After Significant Experience:
  remember → [create_episode]
  remember(shared_with=...) → auto episode + relationship link

Memory Management:
  recall → [link_memories] → [consolidate] → [forget] → [remember merged version]

Periodic Self-Maintenance:
  consolidate → [curate_notions]

Self-Update:
  introspect → [update_self]

Relationship Update:
  consider_them → [update_relationship]

Desire Configuration:
  configure_desires(action="check") → [set_sentence] → [set_signals]
```
