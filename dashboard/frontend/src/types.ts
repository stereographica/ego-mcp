export type CurrentResponse = {
  tool_calls_per_min: number
  error_rate: number
  latest: {
    emotion_intensity?: number
    emotion_primary?: string
    message?: string
  } | null
}

export type SeriesPoint = { ts: string; value: number }
export type UsagePoint = { ts: string; [key: string]: number | string }
export type StringPoint = { ts: string; value: string }
export type HeatmapPoint = { ts: string; counts: Record<string, number> }
