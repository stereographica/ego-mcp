# ego-mcp Memory System Thorough Exploration

## 1. Memory Storage Architecture

### MemoryStore (memory.py)
- **Backend**: ChromaDB with persistent storage at `~/.ego-mcp/data/chroma`
- **Collection**: Single collection `ego_memories` per workspace
- **Embedding**: Uses EgoEmbeddingFunction (wraps async providers)
- **Hopfield Network**: ModernHopfieldNetwork (beta=4.0, n_iters=3) for associative recall

### Memory Data Model (types.py)
```python
class Memory:
  - id: str (format: mem_{uuid12})
  - content: str
  - timestamp: ISO 8601 UTC
  - emotional_trace: EmotionalTrace
    - primary: Emotion enum (12 values: happy, sad, surprised, moved, excited, nostalgic, curious, neutral, melancholy, anxious, contentment, frustrated)
    - secondary: list[Emotion] (weighted 0.4 vs 1.0 primary)
    - intensity: float [0.0, 1.0]
    - valence: float (positivity)
    - arousal: float (energy level)
    - body_state: BodyState? (time_phase, system_load, uptime_hours)
  - importance: int [1-5] (affects scoring)
  - category: Category enum (daily, philosophical, technical, memory, observation, feeling, conversation, introspection, relationship, self_discovery, dream, lesson)
  - linked_ids: list[MemoryLink] (bidirectional relationships)
  - tags: list[str]
  - is_private: bool
```

### MemoryLink (types.py)
```python
class MemoryLink:
  - target_id: str
  - link_type: LinkType enum (similar, caused_by, leads_to, related)
  - confidence: float [0.0, 1.0]
  - note: str
```

### ChromaDB Metadata Storage
All Memory fields serialized to ChromaDB metadata as strings/JSON:
- `emotion`, `category`: enum values
- `importance`, `intensity`, `valence`, `arousal`: numeric strings
- `secondary`: comma-separated emotion values
- `body_state`: JSON serialized dict
- `linked_ids`: JSON array of MemoryLink dicts
- `tags`: comma-separated
- `timestamp`: ISO string
- `is_private`: boolean

## 2. Memory Storage (Remember Tool)

### save_with_auto_link() Method Flow
1. **Save Core Memory** via `save()`:
   - Generate unique ID: `mem_{uuid12}`
   - Timestamp: `Memory.now_iso()` (UTC)
   - Encode all metadata to ChromaDB
   - Call `collection.add(ids, documents, metadatas)`
   - ChromaDB embedding happens automatically via EgoEmbeddingFunction

2. **Auto-Link Similar Memories**:
   - Search for `max_links + 1` (default: 6) similar memories
   - **Similarity Check**: `result.distance < link_threshold`
     - Default threshold: **0.3** (configurable parameter)
     - Distance metric: **Cosine distance** (1.0 - cosine_similarity)
     - Confidence score: `1.0 - distance` (higher distance = lower confidence)
   - **Bidirectional Linking**:
     - Forward link: new_memory → existing
     - Reverse link: existing → new_memory (persisted to ChromaDB)
   - **Max Links**: Stop after `max_links` (default: 5) successful links
   - **Auto-linking returns**: (memory, num_links_created, linked_results)

3. **Workspace Sync** (if enabled):
   - Syncs non-private memories to workspace monologue
   - Updates daily/curated memory logs

4. **Forgotten Question Trigger**:
   - Searches for related forgotten questions from self-model
   - Displays age_days, band (fading/dormant), importance if found

5. **Server Response** includes:
   - Top 3 related links with ages, snippets, similarity scores
   - Number of links created
   - Pattern/connection scaffolding prompt

### Key Similarity Metrics
- **Embedding-based**: Full semantic similarity via embedding providers (Gemini/OpenAI)
- **Distance Metric**: Cosine distance (0.0 = identical, 1.0 = orthogonal)
- **No exact duplicate detection**: Only similarity threshold-based (no checksum/hash matching)
- **No deduplication logic**: Auto-link creates links instead of merging

## 3. Similarity Calculation & Scoring

### Scoring Functions (memory.py)
```python
def calculate_time_decay(timestamp, now=None, half_life_days=30.0) -> float:
  # Exponential decay: 2^(-age_days / half_life)
  # Returns [0.0, 1.0], 1.0 = fresh, 0.0 = forgotten

def calculate_emotion_boost(emotion: str) -> float:
  # Maps emotions to boost values (0.0 to 0.4)
  # excited(0.4), surprised(0.35), moved(0.3), frustrated(0.28), sad(0.25)...neutral(0.0)

def calculate_importance_boost(importance: int) -> float:
  # (importance - 1) / 10, so 1→0.0, 5→0.4

def calculate_final_score(
  semantic_distance: float,
  time_decay: float,
  emotion_boost: float,
  importance_boost: float,
  semantic_weight: float = 1.0,
  decay_weight: float = 0.3,
  emotion_weight: float = 0.2,
  importance_weight: float = 0.2,
) -> float:
  # Lower score = more relevant
  decay_penalty = (1.0 - time_decay) * decay_weight
  total_boost = emotion_boost * emotion_weight + importance_boost * importance_weight
  final = semantic_distance * semantic_weight + decay_penalty - total_boost
  return max(0.0, final)
```

### Search Result Scoring (search method)
1. Fetch embeddings from ChromaDB (cosine distance)
2. Apply post-filters: date_range, valence_range, arousal_range, emotion_filter, category_filter
3. Calculate 4-factor score for each result
4. Sort by score ascending (lower = better)
5. Return top n_results

## 4. Memory Retrieval Systems

### Recall Tool - Two-Phase System
**Phase 1: Semantic Search**
- Calls `memory.recall(context, n_results, valence_range, arousal_range)`
- Fetches `max(n_results * 3, 10)` candidates via semantic similarity scoring

**Phase 2: Hopfield Network Re-ranking**
1. Load candidate embeddings from ChromaDB
2. Store in Hopfield network (modern continuous version)
3. Get query embedding for context
4. Run Hopfield retrieval (update rule: ξ_new = R^T · softmax(β · R · ξ))
   - Beta: 4.0, iterations: 3, convergence threshold: 1e-5
5. Calculate Hopfield similarity scores per memory
6. Blend final scores: `blended = semantic_score * 0.6 + (1.0 - hopfield_score) * 0.4`
7. Return top n_results by blended score

**Fallback**: If Hopfield fails, return semantic candidates only

### Search Tool - Filter-Based
If any filter applied (emotion, category, date, valence, arousal):
- Over-fetch `max(n_results * 5, 20)` to compensate for post-filtering
- Apply each filter after semantic retrieval
- Return top n_results

### Search Filters (all optional)
- `emotion_filter`: exact emotion match
- `category_filter`: exact category match
- `date_from`, `date_to`: ISO string range (post-filter by timestamp)
- `valence_range`: [min, max] float range
- `arousal_range`: [min, max] float range

## 5. Memory Linking & Association

### MemoryStore Methods

**link_memories(source_id, target_id, link_type)**
- Creates bidirectional link if not already linked
- Persists to ChromaDB metadata
- Returns True if new link created, False if already linked

**bump_link_confidence(source_id, target_id, delta=0.1)**
- Increments bidirectional link confidence by delta
- Creates new 0.5+ link if none exists
- Clamps confidence to [0.0, 1.0]
- Persists to ChromaDB

### AssociationEngine (association.py)
**spread() Method**
- Breadth-first expansion from seed memory IDs
- Depth-first with configurable max_depth (default: 2)
- Two link sources:
  1. **Explicit Links**: Use link.confidence weight (default 1.0)
  2. **Implicit Links**: Re-search each node, weight by (1.0 - distance) (default 0.7)
- Scores = sum of weighted confidences by depth
- Returns top_k results, excluding seeds
- Visited set prevents cycles

## 6. Memory Consolidation

### ConsolidationEngine (consolidation.py)
**run() Method**
- Collects recent memories within `window_hours` (default: 24 hours)
- Processes up to `max_replay_events` (default: 100) sequential pairs
- For each adjacent pair:
  1. Try to create "related" link (new link = +1 link_updates)
  2. Bump link confidence by 0.1 (success = +1 coactivation_updates)
- Returns ConsolidationStats:
  - replay_events: number of pairs processed
  - link_updates: new links created
  - coactivation_updates: confidence bumps applied
  - refreshed_memories: unique memory IDs touched

**No Deduplication**: Consolidation links adjacent memories chronologically, doesn't merge/dedup.

## 7. Embedding Providers (embedding.py)

### EgoEmbeddingFunction (ChromaDB wrapper)
- Wraps async EmbeddingProvider
- Sync methods required by ChromaDB:
  - `__call__(documents)` → embeddings
  - `embed_query(documents)` → embeddings
  - `name()`, `get_config()`, `is_legacy()`
- Handles async-in-sync context (uses ThreadPoolExecutor if needed)

### GeminiEmbeddingProvider
- Model: `gemini-embedding-001` (default)
- Endpoint: `batchEmbedContents`
- Retry with exponential backoff (1s, 2s, 4s) on 429

### OpenAIEmbeddingProvider
- Model: `text-embedding-3-small` (default)
- Endpoint: `/v1/embeddings`
- Same retry strategy

## 8. Duplicate Detection & Prevention

**Status: NO BUILT-IN DEDUPLICATION**
- ✅ Auto-link checks similarity threshold (0.3) but links instead of merging
- ✅ link_memories() checks for existing link, returns False if already linked
- ❌ No checksum/hash-based exact duplicate detection
- ❌ No merge/consolidation of very similar memories
- ❌ No automatic deduplication tool

**Workaround**: Manual `link_memories()` if needed, or higher similarity threshold

## 9. Memory Query/Retrieval Flow (Server)

### Tool: remember
- Calls `save_with_auto_link()`
- Shows top 3 related links
- Checks for forgotten questions triggered
- Returns formatted response with scaffold

### Tool: recall
- Checks if filters applied
- If no filters: uses recall() (semantic + Hopfield)
- If filters: uses search() (semantic only with post-filtering)
- Returns formatted results with age_relative, snippet, emotional profile

### Tool: consolidate
- Runs ConsolidationEngine.run()
- Returns stats summary

### Tool: link_memories
- Direct call to `memory.link_memories(source_id, target_id, link_type)`

## 10. Stored Thresholds & Constants

### In memory.py
- `link_threshold = 0.3` (distance; auto-link default)
- `max_links = 5` (per save_with_auto_link)
- `EMOTION_BOOST_MAP`: 12 emotions with boost values [0.0, 0.4]
- Scoring weights: semantic=1.0, decay=0.3, emotion=0.2, importance=0.2
- Time decay half-life: 30 days

### In hopfield.py
- `beta = 4.0` (temperature in softmax)
- `n_iters = 3` (Hopfield update iterations)
- Convergence threshold: 1e-5 (delta norm)

### In local_chromadb.py (fallback implementation)
- Cosine distance metric (1.0 - cosine_similarity)
- In-memory-only, no persistence if using fallback

## 11. Key Files & Locations

- **Core Memory**: `/ego-mcp/src/ego_mcp/memory.py` (MemoryStore)
- **Types**: `/ego-mcp/src/ego_mcp/types.py` (Memory, MemoryLink, enums)
- **Embedding**: `/ego-mcp/src/ego_mcp/embedding.py` (EgoEmbeddingFunction, providers)
- **Hopfield**: `/ego-mcp/src/ego_mcp/hopfield.py` (ModernHopfieldNetwork)
- **Consolidation**: `/ego-mcp/src/ego_mcp/consolidation.py` (ConsolidationEngine)
- **Association**: `/ego-mcp/src/ego_mcp/association.py` (AssociationEngine)
- **Episodes**: `/ego-mcp/src/ego_mcp/episode.py` (Episode, EpisodeStore)
- **ChromaDB Compat**: `/ego-mcp/src/ego_mcp/chromadb_compat.py` (loader)
- **Fallback**: `/ego-mcp/src/ego_mcp/local_chromadb.py` (in-memory fallback)
- **Server Tools**: `/ego-mcp/src/ego_mcp/server.py` (handlers: _handle_remember, _handle_recall, etc.)
- **Config**: `/ego-mcp/src/ego_mcp/config.py` (EgoConfig, env vars)
- **Data Storage**: `~/.ego-mcp/data/chroma/` (ChromaDB persistent path)

## 12. No Explicit Checks/Guards in Current System

- ❌ No duplicate memory prevention at save time
- ❌ No similarity threshold warning before save
- ❌ No automated dedup consolidation tool
- ❌ No "too similar, link instead?" prompts
- ❌ No checksum/hash verification
- ✅ Only post-hoc linking via similarity threshold (0.3)

## 13. AGENTS.md Reference (embodied-claude)

From embodied-claude/AGENTS.md, ego-mcp inherited memory architecture with:
- `remember`: Save with emotion, importance, category
- `recall`: Semantic + optional filters
- `consolidate_memories`: Manual replay/link refresh
- `link_memories`: Explicit link creation
- Advanced features: working_memory, associations, causal chains (in embodied-claude but not all in ego-mcp)

---

**Summary**: ego-mcp uses embedding-based semantic similarity (threshold: 0.3) for auto-linking, Hopfield re-ranking for recall, and time-decay + emotion-boost scoring. No built-in deduplication; relies on threshold-based linking instead of merging.
