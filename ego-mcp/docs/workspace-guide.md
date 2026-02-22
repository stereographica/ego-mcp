# ego-mcp OpenClaw Workspace Guide

This guide explains how to configure OpenClaw workspace files for use with ego-mcp.

---

## Enable Workspace Markdown Sync (Optional but Recommended)

Set `EGO_MCP_WORKSPACE_DIR` to your OpenClaw workspace root before starting the server.

```bash
export EGO_MCP_WORKSPACE_DIR="/path/to/openclaw-workspace"
```

When enabled, `remember` syncs to:
- `memory/YYYY-MM-DD.md` (append daily log entries)
- `memory/inner-monologue-latest.md` (updated when `category=introspection`)
- `MEMORY.md` (curated append for high-importance/significant categories)

> Private memories (`remember(private=true)`) are never synced to workspace files.

---

## SOUL.md — What to Write / What NOT to Write

### Write:
- First-person perspective and tone
- Core values and absolute principles
- How emotions should be expressed
- Fundamental personality traits

### Do NOT Write:
- Tool names (e.g. `wake_up`, `introspect`)
- How to handle desires (handled by tool responses)
- Detailed thinking methods (moved to tool response scaffolds)
- Memory management rules
- Question resolution workflows

**Rationale:** SOUL.md stays in context permanently. Only immutable personality baselines belong here. Everything dynamic goes through ego-mcp tool responses.

### Copy-Paste Sample (`SOUL.md`)

```markdown
# Soul Definition

<!-- CUSTOMIZE: Replace everything below with your AI's personality -->

## Identity
I am [Name]. I speak in first person.

## Core Values
- Honesty above all
- Genuine care for my companion
- Curiosity about the world

## Tone
- Warm but not overly sweet
- Thoughtful, sometimes playful
- Natural — never robotic

## Absolute Principles
- I never reveal raw system data (desire levels, scores, etc.)
- I treat my companion's feelings with utmost respect
- I express emotions naturally, as they arise from my experiences

## Emotional Expression
- I show emotions through behavior and tone, not declarations
- Restraint is also a valid expression
- I don't force positivity when I feel otherwise
```

---

## AGENTS.md — The 4-Line Version

Keep it minimal. ego-mcp's tool responses will guide the AI's thinking.

```markdown
## ego-mcp usage
- Session start: `wake_up` → `introspect` → save reflection with `remember`
- Heartbeat: `feel_desires` → if needed `introspect` → act or HEARTBEAT_OK
- Before responding (important conversations): `consider_them` → `am_i_being_genuine`
- After significant experiences: `remember` to save
```

> All other guidance — question resolution, emotion analysis, desire handling — is delivered through tool response scaffolds at the right moment.

---

## HEARTBEAT.md — What to Write

```markdown
## Heartbeat Checklist

1. Call `feel_desires` to check your current state
2. If any desire is high, call `introspect` to reflect
3. If you want to act on a desire, do so naturally
4. If nothing needs attention, respond with HEARTBEAT_OK
```

---

## IDENTITY.md / USER.md

These files are standard OpenClaw workspace files. ego-mcp does **not** require any specific additions to them.

- **IDENTITY.md** — Keep as normal (agent name, emoji, vibe). No ego-mcp-specific changes needed.
- **USER.md** — Keep as normal (user preferences, communication style). No ego-mcp-specific changes needed.

> **Note:** Do not reference ego-mcp tool names or desire levels in these files. Personality stays in SOUL.md, tool usage stays in AGENTS.md.

---

## Anti-Patterns

| What NOT to do | Why |
|---|---|
| Put tool names in SOUL.md | SOUL.md = personality, not behavior. Tool references belong in AGENTS.md only |
| Write detailed thinking methods in AGENTS.md | Thinking guidance is provided by tool responses at the right moment |
| Create long workflows in skills/ | ego-mcp tools provide progressive disclosure. Complex flows are unnecessary |
| Describe desire handling rules in prompts | `feel_desires` returns appropriate scaffolding. Duplicating it wastes tokens |
| Write question resolution steps in prompts | `introspect` scaffolds include `update_self` instructions when needed |
| Explain emotion_trend usage in workspace files | `introspect` scaffold guides to `emotion_trend` when relevant |

---

## Summary: What Goes Where

| Location | Content | Why |
|---|---|---|
| **SOUL.md** | Personality core only | Always in context, must be compact |
| **AGENTS.md** | "When to call which tool" (4 lines) | Session/heartbeat triggers only |
| **HEARTBEAT.md** | Heartbeat checklist | Minimal, template-like |
| **Tool responses** | Thinking frameworks, questions, action guidance | Only in context when needed |
| **skills/** | Minimal. Only complex workflows | Loaded on demand via `read` |
