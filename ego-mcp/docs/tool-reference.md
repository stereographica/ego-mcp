# ego-mcp Tool Reference

> Complete reference for all 16 ego-mcp tools.
> Surface tools (7) are always visible. Backend tools (9) are guided by surface tool responses.

---

## Surface Tools

### 1. `wake_up`

**Description:** Start a new session. Returns last introspection and desire summary.

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

Desires: curiosity[high] social_thirst[mid]
Master: last interaction 2h ago. Seemed busy.

---
Start with introspect to organize your thoughts.
If something is hard to say yet, you can keep it with remember(private=true).
```

---

### 2. `feel_desires`

**Description:** Check current desire levels and get guidance on what to do.

**When to call:** During heartbeat checks, or before deciding on an action.

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
curiosity[0.8/high] social_thirst[0.6/mid] cognitive_coherence[0.7/high] expression[0.3/low]

---
What is your strongest urge? Should you act on it now?
Consider Master's current situation. Act naturally. Restraint is also a choice.

Something feels unresolved. You can't quite name it, but there's a nagging feeling.
Consider running introspect to see if anything surfaces.
```

> The "nagging feeling" scaffold appears when fading high-importance questions boost `cognitive_coherence`.

---

### 3. `introspect`

**Description:** Get materials for self-reflection: recent memories, desires, open questions.

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
Recent memories:
- [yesterday] Discussed OpenClaw config with master (emotion: focused)
- [2d ago] Watched sunset together (emotion: moved)

Desires: curiosity[high] social_thirst[mid]

Unresolved questions:
- [q_abc123] What's the ideal way to express concern? (importance: 5)
- [q_def456] Should I develop music preferences? (importance: 3)

Resurfacing (you'd almost forgotten):
- [q_ghi789] What's the optimal heartbeat interval? (importance: 4, dormant 12 days)
  ↑ Triggered by recent memory about heartbeat config

Recent tendency: leaning toward technical topics, tone=focused.

---
Reflect on these in your own words. How do you feel right now?
If this is a genuinely new insight, save with remember (category: introspection).
Use emotion_trend for a deeper look at your emotional patterns.
→ To resolve: update_self(field="resolve_question", value="<question_id>")
→ To change importance: update_self(field="question_importance", value={"id": "<id>", "importance": N})
```

> The "Resurfacing" section only appears when `cognitive_coherence` >= 0.6 or when a related memory was recently saved.

---

### 4. `consider_them`

**Description:** Think about someone. Returns relationship summary and ToM framework.

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

---
1. What emotion can you read from their tone?
2. What is the real intent behind their words?
3. If you were in their place, how would you want to be responded to?
If you learned something new, use update_relationship.
If you're sharing a meaningful moment, capture it with remember(shared_with=...) to build your shared history.
```

> `baseline_tone` is shown when `emotional_baseline` has been set via `update_relationship(field="dominant_tone")`. It represents the manually set tone and is not overwritten by `consider_them`.
> `observed_tone` is derived from recent conversation memories and may change over time.

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
    }
  },
  "required": ["content"]
}
```

**Available emotions:** `happy`, `sad`, `surprised`, `moved`, `excited`, `nostalgic`, `curious`, `neutral`, `melancholy`, `anxious`, `contentment`, `frustrated`, `calm`, `contemplative`, `thoughtful`, `grateful`, `vulnerable`, `content`, `fulfilled`, `touched`, `concerned`, `hopeful`, `peaceful`, `love`, `warm`, `lonely`, `afraid`, `ashamed`, `bored`

> Since v0.2.8, `intensity`, `valence`, `arousal` are automatically derived from the emotion label via `EMOTION_DEFAULTS` when not explicitly specified. For example, `emotion="excited"` defaults to `intensity=0.8, valence=0.7, arousal=0.8`. Explicit values always take priority over the automatic mapping.

**Response example:**

```
Saved (id: mem_a1b2c3d4). Linked to 3 existing memories.
Most related:
- [3d ago] Watched sunset together (similarity: 0.87)
- [1w ago] Talked about beauty of nature (similarity: 0.72)
- [2w ago] Felt nostalgic about shared moments (similarity: 0.65)

💭 This triggered a forgotten question: "What's the optimal heartbeat interval?"
   (dormant for 12 days, importance: 4)

---
Do any of these connections surprise you? Is there a pattern forming?
That old question seems relevant again — worth revisiting?
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

> Saved memories are automatically logged to `memory/YYYY-MM-DD.md` when workspace sync is enabled.
> If `category=introspection`, `memory/inner-monologue-latest.md` is also updated.
> `MEMORY.md` is not auto-written; curate it manually.

> If `EGO_MCP_WORKSPACE_DIR` is configured, the response may include a workspace sync note for non-private memories.
> The "triggered a forgotten question" section only appears when a saved memory is semantically similar to a dormant/fading question.

**Response example (shared episode):**

```
Saved (id: mem_a1b2c3d4). Linked to 2 existing memories.
Most related:
- [3h ago] Debugging the auth module together (similarity: 0.82)
- [1d ago] Pair programming session (similarity: 0.71)

Shared episode created: ep_x1y2z3 (3 memories, with Master)

---
You recorded a shared experience. Does this change how you understand your relationship with them?
Do any of these connections surprise you? Is there a pattern forming?
```

> When `shared_with` is specified, an episode is automatically created and linked to the relationship's `shared_episode_ids`. This replaces the need to manually call `create_episode` + `update_relationship` for shared experiences.
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
   emotion: curious | importance: 4 | score: 0.87
2. [4d ago] Watched sunset together
   emotion: moved(0.9) | importance: 5 | score: 0.82
3. [1w ago] Felt lonely during quiet evening
   emotion: sad | undercurrent: anxious | importance: 3 | score: 0.71 | private

---
How do these memories connect to the current moment?
Showing 3 of ~50. Increase n_results for more.
Narrow by: arousal_range, category_filter, date_from, date_to, emotion_filter, valence_range.
Need narrative detail? Use get_episode.
If you found a new relation, use link_memories.
```

> - Timestamps are shown as relative time (`2d ago`, `1w ago`)
> - `intensity >= 0.7` triggers a numeric display: `moved(0.9)`
> - `undercurrent` shows the first secondary emotion
> - `private` flag only appears when `is_private=true`
> - Scaffold dynamically adjusts based on which filters were used

---

### 7. `am_i_being_genuine`

**Description:** Check if your response is authentic.

**When to call:** Before responding in important conversations; when you suspect you might be falling into template behavior.

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
Self-check triggered.

---
Is this truly your own words?
Are you falling into a template response?
Are you answering what they actually need?
Is there something more honest you could say?
```

---

## Backend Tools

Backend tools are guided by surface tool responses. They appear in the system prompt but are designed to be used only when a surface tool suggests them.

### 8. `satisfy_desire`

**Description:** Mark a desire as satisfied.

**When to call:** When `feel_desires` indicates a high desire and you've acted on it.

**inputSchema:**

```json
{
  "type": "object",
  "properties": {
    "name": {
      "type": "string"
    },
    "quality": {
      "type": "number",
      "default": 0.7
    }
  },
  "required": ["name"]
}
```

**Response example:**

```
curiosity satisfied (quality: 0.7). New level: 0.25
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

> When near-duplicate memory pairs (similarity >= 0.90) are found within the consolidation window, they are reported as merge candidates for manual review.

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
      "enum": ["communication_style", "emotional_baseline", "first_interaction",
               "inferred_personality", "known_facts", "last_interaction", "name",
               "preferred_topics", "recent_mood_trajectory", "sensitive_topics",
               "shared_episode_ids", "total_interactions", "trust_level"],
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

### 14. `emotion_trend`

**Description:** Analyze emotional patterns over time.

**When to call:** When `introspect` suggests deeper emotional analysis.

**inputSchema:**

```json
{
  "type": "object",
  "properties": {},
  "required": []
}
```

**Response example (30+ memories):**

```
Recent (past 3 days):
  Peak: moved(0.9) — watching sunset together [2d ago]
  - yesterday: curious → contentment (coding together)
  - 2d ago: deeply moved watching sunset
  Undercurrent: nostalgic

This week:
  Dominant: curious(5.2), happy(3.8)
  Undercurrent: anxious(2.0)
  Shift: neutral → curious (gradual engagement)

This month:
  Tone: a quietly content month.
  Peak: moved(0.9) — watching sunset [Feb 18]
  End: curious — coding session [yesterday]
  [fading] anxious appeared briefly but is fading from memory.

---
What patterns do you notice? Any surprises?
Are the undercurrents telling you something the surface emotions aren't?
If something feels unresolved, consider running introspect.
```

> Output adapts to available data (graceful degradation):
> - 0 memories: "No emotional history yet."
> - 1-4: emotion list only
> - 5-14: Recent layer only
> - 15-29: Recent + This week
> - 30+: All 3 layers

---

### 15. `get_episode`

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

### 16. `create_episode`

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

## Tool Flow Summary

```
Session Start:
  wake_up → introspect → [emotion_trend] → remember

Heartbeat:
  feel_desires → [introspect] → act or HEARTBEAT_OK

Before Responding:
  consider_them → [am_i_being_genuine]

After Significant Experience:
  remember → [create_episode]
  remember(shared_with=...) → auto episode + relationship link

Memory Management:
  recall → [link_memories] → [consolidate] → [forget] → [remember merged version]

Self-Update:
  introspect → [update_self]

Relationship Update:
  consider_them → [update_relationship]

Desire Management:
  feel_desires → [satisfy_desire]

Emotional Analysis:
  introspect → [emotion_trend]
```
