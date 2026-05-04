export type CurrentResponse = {
  tool_calls_per_min: number
  error_rate: number
  window_24h?: {
    tool_calls: number
    error_rate: number
  }
  latest_desires?: Record<string, number>
  latest_emergent_desires?: Record<string, number>
  latest_emotion?: {
    ts: string
    emotion_primary?: string
    emotion_intensity?: number
    valence?: number
    arousal?: number
  } | null
  latest_relationship?: {
    trust_level?: number
    total_interactions?: number
    shared_episodes_count?: number
  } | null
  latest: {
    ts?: string
    emotion_intensity?: number
    emotion_primary?: string
    message?: string
    duration_ms?: number
    tool_name?: string
    string_metrics?: Record<string, string>
    numeric_metrics?: Record<string, number>
  } | null
}

export type DesireCatalogItem = {
  id: string
  display_name: string
  maslow_level: number
}

export type DesireCatalogResponse = {
  items: DesireCatalogItem[]
}

export type AnomalyAlert = {
  kind: 'usage_spike' | 'intensity_spike'
  ts: string
  value: number
}

export type TimeRangePreset = '15m' | '1h' | '6h' | '24h' | '7d' | 'custom'

export type DateRange = {
  from: string
  to: string
}

export type SeriesPoint = { ts: string; value: number }
export type IntensityPoint = SeriesPoint & { emotion_primary?: string }
export type EmotionTrendPoint = SeriesPoint & { emotion_primary?: string }
export type UsagePoint = { ts: string; [key: string]: number | string }
export type StringPoint = { ts: string; value: string }
export type HeatmapPoint = { ts: string; counts: Record<string, number> }
export type HistoryMarkerKind = 'proust' | 'impulse' | 'emergent'
export type HistoryMarker = {
  ts: string
  kind: HistoryMarkerKind
  label: string
  detail?: string
  value?: number
  confidence?: number
  memory_id?: string
  desire_key?: string
}
export type TextMetaField = {
  type: 'text'
  value: string
}

export type FilePathMetaField = {
  type: 'file_path'
  path: string
}

export type NotionIdsMetaField = {
  type: 'notion_ids'
  notion_ids: string[]
}

export type MetaField = TextMetaField | FilePathMetaField | NotionIdsMetaField

export type MemoryNetworkNode = {
  id: string
  label?: string
  category: string
  is_notion: boolean
  content_preview?: string | null
  importance?: number | null
  tags?: string[]
  is_private?: boolean
  confidence?: number
  emotion_tone?: string | null
  access_count?: number
  decay?: number
  reinforcement_count?: number
  source_count?: number | null
  person_id?: string
  related_count?: number
  is_conviction?: boolean
  degree: number
  betweenness: number
  emotional_valence?: number | null
  emotional_arousal?: number | null
  last_accessed?: string | null
  created?: string | null
  last_reinforced?: string | null
  meta_fields?: Record<string, MetaField>
}
export type MemoryNetworkEdge = {
  source: string
  target: string
  link_type: string
  confidence?: number
}
export type MemoryNetworkStats = {
  node_count: number
  memory_count: number
  notion_count: number
  edge_count: number
  conviction_count: number
  avg_memory_decay: number
  graph_density: number
  top_hub_id?: string
  top_hub_degree: number
  top_category?: string
  top_category_ratio: number
}
export type MemoryNetworkResponse = {
  nodes: MemoryNetworkNode[]
  edges: MemoryNetworkEdge[]
  stats: MemoryNetworkStats
}
export type MemoryDetail = {
  id: string
  content: string
  timestamp: string
  category: string
  importance: number
  tags?: string[]
  is_private: boolean
  access_count: number
  last_accessed: string
  decay: number
  emotional_trace: {
    valence: number
    arousal: number
    intensity: number
  }
  linked_ids: Array<{
    target_id: string
    link_type: string
    confidence: number
    note?: string
  }>
  generated_notion_ids: string[]
}
export type MemoryNetworkPath = {
  node_ids: string[]
  edge_pairs: [string, string][] | string[][]
  length: number
  exists: boolean
}
export type MemoryGraphFilters = {
  showMemories: boolean
  showNotions: boolean
  convictionsOnly: boolean
  categories: string[]
  minImportance: number
  minConfidence: number
  minDecay: number
}
export type Notion = {
  id: string
  label: string
  emotion_tone: string
  confidence: number
  tags?: string[]
  source_count: number
  source_memory_ids: string[]
  related_notion_ids: string[]
  related_count: number
  reinforcement_count: number
  person_id: string
  is_conviction: boolean
  created: string
  last_reinforced: string
  meta_fields?: Record<string, MetaField>
}
export type LogPoint = {
  ts: string
  level: string
  logger: string
  message: string
  private: boolean
  fields?: Record<string, unknown>
  [key: string]: unknown
}

export type LogLine = {
  ts: string
  tool_name?: string
  ok: boolean
  level?: string
  logger?: string
  message?: string
}

export type PersonOverview = {
  person_id: string
  name: string
  relation_kind: 'interlocutor' | 'mentioned'
  trust_level: number | null
  total_interactions: number
  shared_episodes_count: number
  last_interaction: string | null
  first_interaction: string | null
  aliases: string[]
}

export type PersonDetail = {
  person_id: string
  trust_history: Array<{ ts: string; value: number }>
  shared_episodes_history: Array<{ ts: string; value: number }>
  surface_counts: { resonant: number; involuntary: number; total: number }
}

export type SurfaceTimelinePoint = {
  ts: string
  person_id: string
  surface_type: 'resonant' | 'involuntary'
}
