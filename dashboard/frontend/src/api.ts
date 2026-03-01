import type {
  AnomalyAlert,
  CurrentResponse,
  DateRange,
  HeatmapPoint,
  LogLine,
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

const toLogLine = (item: LogPoint): LogLine => {
  const fields =
    typeof item.fields === 'object' && item.fields !== null
      ? (item.fields as Record<string, unknown>)
      : {}
  const level = typeof item.level === 'string' ? item.level : undefined
  const message = typeof item.message === 'string' ? item.message : undefined
  const toolName =
    typeof item.tool_name === 'string'
      ? item.tool_name
      : typeof fields.tool_name === 'string'
        ? fields.tool_name
        : undefined

  return {
    ts: String(item.ts ?? new Date().toISOString()),
    tool_name: toolName,
    ok:
      typeof item.ok === 'boolean'
        ? item.ok
        : !(level === 'ERROR' || message === 'Tool execution failed'),
    level,
    logger: typeof item.logger === 'string' ? item.logger : undefined,
    message,
  }
}

export const fetchCurrent = async (): Promise<CurrentResponse> =>
  get('/api/v1/current', {
    tool_calls_per_min: 0,
    error_rate: 0,
    window_24h: { tool_calls: 0, error_rate: 0 },
    latest_desires: {},
    latest_emotion: null,
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

export async function fetchLogs(): Promise<LogLine[]>
export async function fetchLogs(
  range: DateRange,
  level: string,
  search: string,
): Promise<LogPoint[]>
export async function fetchLogs(
  range?: DateRange,
  level = 'ALL',
  search = '',
): Promise<LogLine[] | LogPoint[]> {
  if (range == null) {
    const now = new Date()
    const fiveMinAgo = new Date(now.getTime() - 5 * 60 * 1000)
    const data = await get<{ items: LogPoint[] }>(
      `/api/v1/logs?from=${encodeURIComponent(fiveMinAgo.toISOString())}&to=${encodeURIComponent(now.toISOString())}`,
      { items: [] },
    )
    return (data.items ?? []).map(toLogLine)
  }

  const levelQuery = level === 'ALL' ? '' : `&level=${level}`
  const searchQuery = search ? `&search=${encodeURIComponent(search)}` : ''
  const data = await get<{ items: LogPoint[] }>(
    `/api/v1/logs?${encodeRange(range)}${levelQuery}${searchQuery}`,
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
