import type {
  CurrentResponse,
  HeatmapPoint,
  SeriesPoint,
  StringPoint,
  UsagePoint,
} from './types'

const BASE = import.meta.env.VITE_DASHBOARD_API_BASE ?? 'http://localhost:8000'
const NOW_FROM = '2026-01-01T12:00:00Z'
const NOW_TO = '2026-01-01T12:30:00Z'

const get = async <T>(path: string, fallback: T): Promise<T> => {
  try {
    const res = await fetch(`${BASE}${path}`)
    if (!res.ok) return fallback
    return (await res.json()) as T
  } catch {
    return fallback
  }
}

export const fetchCurrent = async (): Promise<CurrentResponse> =>
  get('/api/v1/current', {
    tool_calls_per_min: 0,
    error_rate: 0,
    latest: { emotion_primary: 'n/a', emotion_intensity: 0 },
  })

export const fetchIntensity = async (): Promise<SeriesPoint[]> => {
  const data = await get<{ items: SeriesPoint[] }>(
    `/api/v1/metrics/intensity?from=${NOW_FROM}&to=${NOW_TO}&bucket=1m`,
    { items: [] },
  )
  return data.items
}

export const fetchUsage = async (): Promise<UsagePoint[]> => {
  const data = await get<{ items: UsagePoint[] }>(
    `/api/v1/usage/tools?from=${NOW_FROM}&to=${NOW_TO}&bucket=5m`,
    { items: [] },
  )
  return data.items
}

export const fetchTimeline = async (): Promise<StringPoint[]> => {
  const data = await get<{ items: StringPoint[] }>(
    `/api/v1/metrics/time_phase/string-timeline?from=${NOW_FROM}&to=${NOW_TO}`,
    { items: [] },
  )
  return data.items
}

export const fetchHeatmap = async (): Promise<HeatmapPoint[]> => {
  const data = await get<{ items: HeatmapPoint[] }>(
    `/api/v1/metrics/time_phase/heatmap?from=${NOW_FROM}&to=${NOW_TO}&bucket=5m`,
    { items: [] },
  )
  return data.items
}
