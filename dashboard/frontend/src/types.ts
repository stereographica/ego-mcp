export type CurrentResponse = {
  tool_calls_per_min: number
  error_rate: number
  latest: {
    emotion_intensity?: number
    emotion_primary?: string
    message?: string
  } | null
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
