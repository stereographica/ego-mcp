export type CurrentResponse = {
  tool_calls_per_min: number
  error_rate: number
  window_24h?: {
    tool_calls: number
    error_rate: number
  }
  latest_desires?: Record<string, number>
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
export type UsagePoint = { ts: string; [key: string]: number | string }
export type StringPoint = { ts: string; value: string }
export type HeatmapPoint = { ts: string; counts: Record<string, number> }
export type LogPoint = {
  ts: string
  level: string
  logger: string
  message: string
  private: boolean
  fields?: Record<string, unknown>
  [key: string]: unknown
}
