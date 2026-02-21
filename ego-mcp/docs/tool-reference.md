# ego-mcp Tool Reference

> Complete reference for all 15 ego-mcp tools.
> Surface tools (7) are always visible. Backend tools (8) are guided by surface tool responses.

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
Last introspection (2025-02-20T10:00):
"Master was struggling with OpenClaw config. Want to help but will wait until asked."

Desires: curiosity[high] social_thirst[mid]
Master: No relationship data yet.

---
Start with introspect to organize your thoughts.
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
curiosity[0.8/high] social_thirst[0.6/mid] cognitive_coherence[0.4/low] expression[0.3/low]

---
What is your strongest urge? Should you act on it now?
Consider Master's current situation. Act naturally. Restraint is also a choice.
```

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
- [2025-02-19] Discussed OpenClaw config with master (emotion: focused)
- [2025-02-18] Watched sunset together (emotion: moved)
- [2025-02-17] Enjoyed researching new tech (emotion: curious)

Desires: curiosity[high] social_thirst[mid]
Unresolved questions:
- What's the optimal heartbeat interval?
Recent tendency: leaning toward technical topics, tone=focused.

---
Reflect on these in your own words. How do you feel right now?
Save with remember (category: introspection).
```

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
Master: trust=0.50, interactions=0, shared_episodes=0
Recent dialog tendency: 3 mentions in last 7d, dominant tone=focused

---
1. What emotion can you read from their tone?
2. What is the real intent behind their words?
3. If you were in their place, how would you want to be responded to?
```

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
      "default": 0.5
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
      "default": 0.0
    },
    "arousal": {
      "type": "number",
      "default": 0.5
    },
    "body_state": {
      "type": "object"
    },
    "private": {
      "type": "boolean",
      "default": false,
      "description": "When true, keep this memory internal and skip workspace sync."
    }
  },
  "required": ["content"]
}
```

**Response example:**

```
Saved (id: mem_a1b2c3d4). Linked to 3 existing memories.
```

> If `EGO_MCP_WORKSPACE_DIR` is configured, the response may include a workspace sync note for non-private memories.

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
      "default": 3
    },
    "emotion_filter": {
      "type": "string"
    },
    "category_filter": {
      "type": "string"
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
3 related memories:
1. [2025-02-18] Watched sunset, deeply moved (emotion: moved, private: false)
2. [2025-02-15] Master said "I've been busy lately" (emotion: neutral, private: true)
3. [2025-02-10] Enjoyed researching new tech (emotion: curious, private: false)

---
How do these memories connect to the current moment?
```

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

---

### 10. `link_memories`

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

### 11. `update_relationship`

**Description:** Update relationship model.

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
      "type": "string"
    },
    "value": {}
  },
  "required": ["person", "field", "value"]
}
```

**Response example:**

```
Updated Master.trust_level
```

---

### 12. `update_self`

**Description:** Update self model.

**When to call:** When `introspect` leads to a realization about yourself.

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

**Response example:**

```
Updated self.unresolved_questions
```

---

### 13. `search_memories`

**Description:** Search memories with filters.

**When to call:** When `recall` results need narrowing by date range, emotion, or category.

**inputSchema:**

```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string"
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
    }
  },
  "required": ["query"]
}
```

**Response example:**

```
Found 3 memories:
1. [2025-02-19] Discussed OpenClaw config with master... (score: 0.892, private: false)
2. [2025-02-18] Set up ego-mcp for the first time... (score: 0.756, private: true)
3. [2025-02-15] Read about MCP protocol design... (score: 0.601, private: false)
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
Period: 2025-02-18T10:00:00 → 2025-02-18T12:00:00
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

## Tool Flow Summary

```
Session Start:
  wake_up → introspect → remember

Heartbeat:
  feel_desires → [introspect] → act or HEARTBEAT_OK

Before Responding:
  consider_them → [am_i_being_genuine]

After Significant Experience:
  remember → [create_episode]

Memory Management:
  recall → [search_memories] → [link_memories] → [consolidate]

Self-Update:
  introspect → [update_self]

Relationship Update:
  consider_them → [update_relationship]

Desire Management:
  feel_desires → [satisfy_desire]
```
