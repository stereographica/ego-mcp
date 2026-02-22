import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import {
  fetchCurrent,
  fetchHeatmap,
  fetchIntensity,
  fetchLogs,
  fetchMetric,
  fetchTimeline,
  fetchUsage,
} from './api'
import { Badge } from './components/ui/badge'
import { Card } from './components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from './components/ui/tabs'
import type {
  CurrentResponse,
  DateRange,
  HeatmapPoint,
  LogPoint,
  SeriesPoint,
  StringPoint,
  TimeRangePreset,
  UsagePoint,
} from './types'

const DESIRE_METRIC_KEYS = [
  'information_hunger',
  'social_thirst',
  'cognitive_coherence',
  'pattern_seeking',
  'predictability',
  'recognition',
  'resonance',
  'expression',
  'curiosity',
] as const

type DesireMetricKey = (typeof DESIRE_METRIC_KEYS)[number]
type DesireMetricSeriesMap = Record<DesireMetricKey, SeriesPoint[]>

const makeEmptyDesireMetricSeriesMap = (): DesireMetricSeriesMap => ({
  information_hunger: [],
  social_thirst: [],
  cognitive_coherence: [],
  pattern_seeking: [],
  predictability: [],
  recognition: [],
  resonance: [],
  expression: [],
  curiosity: [],
})

const formatMetricLabel = (key: string) => key.replaceAll('_', ' ')

const makeRange = (preset: TimeRangePreset): DateRange => {
  const to = new Date()
  const from = new Date(to)
  const map: Record<Exclude<TimeRangePreset, 'custom'>, number> = {
    '15m': 15,
    '1h': 60,
    '6h': 360,
    '24h': 1440,
    '7d': 10080,
  }
  from.setMinutes(
    from.getMinutes() - map[preset as Exclude<TimeRangePreset, 'custom'>],
  )
  return { from: from.toISOString(), to: to.toISOString() }
}

const bucketFor = (preset: TimeRangePreset) =>
  preset === '15m' || preset === '1h' ? '1m' : '5m'

const isNearBottom = (el: HTMLElement, threshold = 24) =>
  el.scrollHeight - el.scrollTop - el.clientHeight <= threshold

const browserTimeZone = () => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

const makeTimestampFormatter = (timeZone: string) =>
  new Intl.DateTimeFormat(undefined, {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })

const formatTimestamp = (value: string, formatter: Intl.DateTimeFormat) => {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return formatter.format(parsed)
}

const TOOL_COLORS = [
  ['#334155', '#94a3b8'],
  ['#1e293b', '#475569'],
  ['#0f766e', '#5eead4'],
  ['#1d4ed8', '#93c5fd'],
  ['#7c3aed', '#c4b5fd'],
  ['#b45309', '#fcd34d'],
  ['#be123c', '#fda4af'],
]

const DESIRE_LINE_COLORS = [
  '#0f766e',
  '#1d4ed8',
  '#7c3aed',
  '#b45309',
  '#be123c',
  '#047857',
  '#4338ca',
  '#a16207',
  '#e11d48',
]

const App = () => {
  const [activeTab, setActiveTab] = useState('now')
  const [preset, setPreset] = useState<TimeRangePreset>('1h')
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo] = useState('')
  const [logLevel, setLogLevel] = useState('ALL')
  const [loggerFilter, setLoggerFilter] = useState('')
  const [autoScroll, setAutoScroll] = useState(true)
  const [logFeedPinned, setLogFeedPinned] = useState(true)

  const [current, setCurrent] = useState<CurrentResponse | null>(null)
  const [intensity, setIntensity] = useState<SeriesPoint[]>([])
  const [usage, setUsage] = useState<UsagePoint[]>([])
  const [timeline, setTimeline] = useState<StringPoint[]>([])
  const [heatmap, setHeatmap] = useState<HeatmapPoint[]>([])
  const [logs, setLogs] = useState<LogPoint[]>([])
  const [desireMetrics, setDesireMetrics] = useState<DesireMetricSeriesMap>(
    makeEmptyDesireMetricSeriesMap,
  )
  const logFeedRef = useRef<HTMLDivElement | null>(null)
  const clientTimeZone = useMemo(() => browserTimeZone(), [])
  const timestampFormatter = useMemo(
    () => makeTimestampFormatter(clientTimeZone),
    [clientTimeZone],
  )

  const range = useMemo<DateRange>(() => {
    if (preset !== 'custom') return makeRange(preset)
    return {
      from: customFrom
        ? new Date(customFrom).toISOString()
        : new Date(Date.now() - 3600_000).toISOString(),
      to: customTo
        ? new Date(customTo).toISOString()
        : new Date().toISOString(),
    }
  }, [preset, customFrom, customTo])

  useEffect(() => {
    let disposed = false

    const loadCurrent = async () => {
      const snapshot = await fetchCurrent()
      if (!disposed) {
        setCurrent(snapshot)
      }
    }

    void loadCurrent()

    let socket: WebSocket | null = null
    try {
      socket = new WebSocket(
        (import.meta.env.VITE_DASHBOARD_WS_BASE ?? 'ws://localhost:8000') +
          '/ws/current',
      )
      socket.onmessage = (evt) => {
        const data = JSON.parse(evt.data) as { type: string; data?: unknown }
        if (data.type === 'current_snapshot' && data.data) {
          setCurrent((data as { data: CurrentResponse }).data)
        }
      }
    } catch {
      socket = null
    }

    const timer = setInterval(loadCurrent, 2000)
    return () => {
      disposed = true
      clearInterval(timer)
      socket?.close()
    }
  }, [])

  useEffect(() => {
    if (activeTab !== 'history') return

    let disposed = false
    const bucket = bucketFor(preset)

    const loadHistory = async () => {
      const [i, u, t, h, ...desireSeries] = await Promise.all([
        fetchIntensity(range, bucket),
        fetchUsage(range, bucket),
        fetchTimeline(range),
        fetchHeatmap(range, bucket),
        ...DESIRE_METRIC_KEYS.map((key) => fetchMetric(key, range, bucket)),
      ])
      if (disposed) return
      setIntensity(i)
      setUsage(u)
      setTimeline(t)
      setHeatmap(h)
      setDesireMetrics({
        information_hunger: desireSeries[0] ?? [],
        social_thirst: desireSeries[1] ?? [],
        cognitive_coherence: desireSeries[2] ?? [],
        pattern_seeking: desireSeries[3] ?? [],
        predictability: desireSeries[4] ?? [],
        recognition: desireSeries[5] ?? [],
        resonance: desireSeries[6] ?? [],
        expression: desireSeries[7] ?? [],
        curiosity: desireSeries[8] ?? [],
      })
    }

    void loadHistory()
    const timer = setInterval(loadHistory, 2000)
    return () => {
      disposed = true
      clearInterval(timer)
    }
  }, [activeTab, range, preset])

  useEffect(() => {
    if (activeTab !== 'logs') return

    let disposed = false
    const loadLogs = async () => {
      const data = await fetchLogs(range, logLevel, loggerFilter)
      if (!disposed) {
        setLogs(data)
      }
    }
    void loadLogs()
    const timer = setInterval(loadLogs, 2000)
    return () => {
      disposed = true
      clearInterval(timer)
    }
  }, [activeTab, range, logLevel, loggerFilter])

  const toolSeriesKeys = useMemo(
    () =>
      Array.from(
        new Set(
          usage.flatMap((row) =>
            Object.keys(row).filter(
              (key) => key !== 'ts' && typeof row[key] === 'number',
            ),
          ),
        ),
      ).sort(),
    [usage],
  )

  const desireChartData = useMemo(() => {
    const byTs = new Map<string, Record<string, number | string>>()
    for (const key of DESIRE_METRIC_KEYS) {
      for (const point of desireMetrics[key]) {
        const row = byTs.get(point.ts) ?? { ts: point.ts }
        row[key] = point.value
        byTs.set(point.ts, row)
      }
    }
    return Array.from(byTs.values()).sort((a, b) =>
      String(a.ts).localeCompare(String(b.ts)),
    )
  }, [desireMetrics])

  const latestDesireValues = useMemo(() => {
    const currentLatest = current?.latest_desires ?? {}
    return DESIRE_METRIC_KEYS.map((key) => {
      const currentValue = currentLatest[key]
      if (typeof currentValue === 'number') {
        return [key, currentValue] as const
      }
      const series = desireMetrics[key]
      const lastPoint = series[series.length - 1]
      return [key, lastPoint?.value] as const
    })
  }, [current, desireMetrics])

  useEffect(() => {
    if (autoScroll && logFeedPinned) {
      const el = logFeedRef.current
      if (el) {
        el.scrollTop = el.scrollHeight
      }
    }
  }, [logs, autoScroll, logFeedPinned])

  return (
    <main className="container">
      <h1>ego-mcp Dashboard</h1>

      <Tabs className="tabs" value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="now">Now</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
          <TabsTrigger value="logs">Logs</TabsTrigger>
        </TabsList>

        {activeTab !== 'now' && (
          <div className="range-controls">
            {(['15m', '1h', '6h', '24h', '7d', 'custom'] as const).map(
              (key) => (
                <button
                  key={key}
                  className={`tab-trigger range-button ${preset === key ? 'is-active' : ''}`}
                  onClick={() => setPreset(key)}
                  aria-pressed={preset === key}
                >
                  {key}
                </button>
              ),
            )}
            {preset === 'custom' && (
              <>
                <input
                  className="range-input"
                  type="datetime-local"
                  value={customFrom}
                  onChange={(e) => setCustomFrom(e.target.value)}
                />
                <input
                  className="range-input"
                  type="datetime-local"
                  value={customTo}
                  onChange={(e) => setCustomTo(e.target.value)}
                />
              </>
            )}
          </div>
        )}

        <TabsContent value="now">
          <div className="grid grid-3">
            <Card>
              <p className="title">tool calls (24h total)</p>
              <p className="value">{current?.window_24h?.tool_calls ?? 0}</p>
            </Card>
            <Card>
              <p className="title">error rate (24h)</p>
              <p className="value">
                {(
                  ((current?.window_24h?.error_rate ?? 0) as number) * 100
                ).toFixed(1)}
                %
              </p>
            </Card>
            <Card>
              <p className="title">latest emotion</p>
              <div className="emotion-row">
                <p className="value">
                  {current?.latest?.emotion_primary ?? 'n/a'}
                </p>
                <div className="emotion-intensity">
                  <p className="metric-mini-label">intensity</p>
                  <Badge>
                    {(current?.latest?.emotion_intensity ?? 0).toFixed(2)}
                  </Badge>
                </div>
              </div>
            </Card>
          </div>

          <Card>
            <h3>Latest desire parameters</h3>
            <div className="latest-metrics-grid">
              {latestDesireValues.map(([key, value]) => (
                <div className="latest-metric-row" key={key}>
                  <span className="latest-metric-name">
                    {formatMetricLabel(key)}
                  </span>
                  <Badge>
                    {typeof value === 'number' ? value.toFixed(3) : 'n/a'}
                  </Badge>
                </div>
              ))}
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="history">
          <div className="history-layout">
            <Card>
              <h3>Tool usage history</h3>
              <ResponsiveContainer width="100%" height={280}>
                <AreaChart data={usage}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="ts" hide />
                  <YAxis />
                  <Tooltip
                    labelFormatter={(value) =>
                      formatTimestamp(String(value), timestampFormatter)
                    }
                  />
                  <Legend />
                  {toolSeriesKeys.map((toolName, index) => {
                    const [stroke, fill] =
                      TOOL_COLORS[index % TOOL_COLORS.length]
                    return (
                      <Area
                        key={toolName}
                        type="monotone"
                        dataKey={toolName}
                        stackId="1"
                        stroke={stroke}
                        fill={fill}
                      />
                    )
                  })}
                </AreaChart>
              </ResponsiveContainer>
            </Card>
            <Card>
              <h3>time_phase timeline + heatmap</h3>
              <p className="helper-text">Timestamps: {clientTimeZone}</p>
              <div className="feed feed-tall">
                {timeline.map((item) => (
                  <div key={item.ts} className="feed-item">
                    <strong title={item.ts}>
                      {formatTimestamp(item.ts, timestampFormatter)}
                    </strong>{' '}
                    <Badge>{item.value}</Badge>
                  </div>
                ))}
                {heatmap.map((item) => (
                  <div key={`heat-${item.ts}`} className="feed-item">
                    <strong title={item.ts}>
                      {formatTimestamp(item.ts, timestampFormatter)}
                    </strong>{' '}
                    {JSON.stringify(item.counts)}
                  </div>
                ))}
              </div>
            </Card>
          </div>

          <div className="history-stack">
            <Card>
              <h3>Intensity history</h3>
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={intensity}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="ts" hide />
                  <YAxis domain={[0, 1]} />
                  <Tooltip
                    labelFormatter={(value) =>
                      formatTimestamp(String(value), timestampFormatter)
                    }
                  />
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke="#0f172a"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </Card>

            <Card>
              <h3>Desire parameter history</h3>
              <ResponsiveContainer width="100%" height={340}>
                <LineChart data={desireChartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="ts" hide />
                  <YAxis domain={[0, 1]} />
                  <Tooltip
                    labelFormatter={(value) =>
                      formatTimestamp(String(value), timestampFormatter)
                    }
                  />
                  <Legend
                    formatter={(value) => formatMetricLabel(String(value))}
                  />
                  {DESIRE_METRIC_KEYS.map((key, index) => (
                    <Line
                      key={key}
                      type="monotone"
                      dataKey={key}
                      stroke={
                        DESIRE_LINE_COLORS[index % DESIRE_LINE_COLORS.length]
                      }
                      dot={false}
                      connectNulls
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
              {desireChartData.length === 0 && (
                <p className="helper-text">
                  No desire metric data in selected range.
                </p>
              )}
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="logs">
          <Card className="logs-card">
            <h3>Live tail</h3>
            <p className="helper-text">Timestamps: {clientTimeZone}</p>
            <div className="logs-controls">
              <select
                value={logLevel}
                onChange={(e) => setLogLevel(e.target.value)}
              >
                <option value="ALL">ALL</option>
                <option value="INFO">INFO</option>
                <option value="WARNING">WARNING</option>
                <option value="ERROR">ERROR</option>
              </select>
              <input
                placeholder="logger"
                value={loggerFilter}
                onChange={(e) => setLoggerFilter(e.target.value)}
              />
              <label>
                <input
                  type="checkbox"
                  checked={autoScroll}
                  onChange={(e) => setAutoScroll(e.target.checked)}
                />
                auto scroll
              </label>
            </div>
            <div
              className="feed log-feed"
              id="log-feed"
              ref={logFeedRef}
              onScroll={(e) => setLogFeedPinned(isNearBottom(e.currentTarget))}
            >
              {logs.map((item, index) => {
                const { ts, ...rest } = item
                return (
                  <div
                    key={`log-${item.ts}-${String(item.logger)}-${index}`}
                    className="feed-item log-row"
                  >
                    <div className="log-ts" title={ts}>
                      {formatTimestamp(ts, timestampFormatter)}
                    </div>
                    <pre className="log-json">
                      {JSON.stringify(rest, null, 2)}
                    </pre>
                  </div>
                )
              })}
              {logs.length === 0 && (
                <div className="feed-item log-empty">
                  No log lines in selected range.
                </div>
              )}
            </div>
            {autoScroll && !logFeedPinned && (
              <p className="helper-text">
                Auto scroll is enabled, but paused because you scrolled away
                from the bottom.
              </p>
            )}
          </Card>
        </TabsContent>
      </Tabs>
    </main>
  )
}

export default App
