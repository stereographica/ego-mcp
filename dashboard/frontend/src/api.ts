import type {
  AnomalyAlert,
  CurrentResponse,
  DateRange,
  HeatmapPoint,
  LogPoint,
  SeriesPoint,
  StringPoint,
  UsagePoint,
} from './types'

const BASE = import.meta.env.VITE_DASHBOARD_API_BASE ?? 'http://localhost:8000'

const get = async <T>(path: string, fallback: T): Promise<T> => {
  try {
    const res = await fetch(`${BASE}${path}`)
    if (!res.ok) return fallback
    return (await res.json()) as T
  } catch {
    return fallback
  }
}

const encodeRange = (range: DateRange) =>
  `from=${encodeURIComponent(range.from)}&to=${encodeURIComponent(range.to)}`

export const fetchCurrent = async (): Promise<CurrentResponse> =>
  get('/api/v1/current', {
    tool_calls_per_min: 0,
    error_rate: 0,
    window_24h: { tool_calls: 0, error_rate: 0 },
    latest_desires: {},
    latest: { emotion_primary: 'n/a', emotion_intensity: 0 },
  })

export const fetchMetric = async (
  key: string,
  range: DateRange,
  bucket: string,
): Promise<SeriesPoint[]> => {
  const data = await get<{ items: SeriesPoint[] }>(
    `/api/v1/metrics/${encodeURIComponent(key)}?${encodeRange(range)}&bucket=${bucket}`,
    { items: [] },
  )
  return data.items
}

export const fetchIntensity = async (
  range: DateRange,
  bucket: string,
): Promise<SeriesPoint[]> => fetchMetric('intensity', range, bucket)

export const fetchUsage = async (
  range: DateRange,
  bucket: string,
): Promise<UsagePoint[]> => {
  const data = await get<{ items: UsagePoint[] }>(
    `/api/v1/usage/tools?${encodeRange(range)}&bucket=${bucket}`,
    { items: [] },
  )
  return data.items
}

export const fetchTimeline = async (
  range: DateRange,
): Promise<StringPoint[]> => {
  const data = await get<{ items: StringPoint[] }>(
    `/api/v1/metrics/time_phase/string-timeline?${encodeRange(range)}`,
    { items: [] },
  )
  return data.items
}

export const fetchHeatmap = async (
  range: DateRange,
  bucket: string,
): Promise<HeatmapPoint[]> => {
  const data = await get<{ items: HeatmapPoint[] }>(
    `/api/v1/metrics/time_phase/heatmap?${encodeRange(range)}&bucket=${bucket}`,
    { items: [] },
  )
  return data.items
}

export const fetchLogs = async (
  range: DateRange,
  level: string,
  logger: string,
): Promise<LogPoint[]> => {
  const levelQuery = level === 'ALL' ? '' : `&level=${level}`
  const loggerQuery = logger ? `&logger=${encodeURIComponent(logger)}` : ''
  const data = await get<{ items: LogPoint[] }>(
    `/api/v1/logs?${encodeRange(range)}${levelQuery}${loggerQuery}`,
    {
      items: [],
    },
  )
  return data.items
}

export const fetchAnomalies = async (
  range: DateRange,
  bucket: string,
): Promise<AnomalyAlert[]> => {
  const data = await get<{ items: AnomalyAlert[] }>(
    `/api/v1/alerts/anomalies?${encodeRange(range)}&bucket=${bucket}`,
    { items: [] },
  )
  return data.items
}

export const fetchValence = async (
  range: DateRange,
  bucket: string,
): Promise<SeriesPoint[]> => fetchMetric('valence', range, bucket)

export const fetchArousal = async (
  range: DateRange,
  bucket: string,
): Promise<SeriesPoint[]> => fetchMetric('arousal', range, bucket)
