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
export type MemoryNetworkNode = {
  id: string
  label?: string
  category: string
  is_notion: boolean
  confidence?: number
  access_count?: number
  decay?: number
  reinforcement_count?: number
  person_id?: string
  related_count?: number
  is_conviction?: boolean
}
export type MemoryNetworkEdge = {
  source: string
  target: string
  link_type: string
  confidence?: number
}
export type MemoryNetworkResponse = {
  nodes: MemoryNetworkNode[]
  edges: MemoryNetworkEdge[]
}
export type Notion = {
  id: string
  label: string
  emotion_tone: string
  confidence: number
  source_count: number
  source_memory_ids: string[]
  related_notion_ids: string[]
  related_count: number
  reinforcement_count: number
  person_id: string
  is_conviction: boolean
  created: string
  last_reinforced: string
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
