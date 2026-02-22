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

const App = () => {
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
    const load = async () => {
      const bucket = bucketFor(preset)
      const [c, i, u, t, h, l] = await Promise.all([
        fetchCurrent(),
        fetchIntensity(range, bucket),
        fetchUsage(range, bucket),
        fetchTimeline(range),
        fetchHeatmap(range, bucket),
        fetchLogs(range, logLevel, loggerFilter),
      ])
      setCurrent(c)
      setIntensity(i)
      setUsage(u)
      setTimeline(t)
      setHeatmap(h)
      setLogs(l)
    }
    void load()

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

    const timer = setInterval(load, 2000)
    return () => {
      clearInterval(timer)
      socket?.close()
    }
  }, [range, preset, logLevel, loggerFilter])

  const feed = useMemo(() => timeline.slice(-8), [timeline])

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

  const totalToolCallsInRange = useMemo(
    () =>
      usage.reduce((sum, row) => {
        const rowTotal = Object.entries(row).reduce((acc, [key, value]) => {
          if (key === 'ts' || typeof value !== 'number') return acc
          return acc + value
        }, 0)
        return sum + rowTotal
      }, 0),
    [usage],
  )

  const toolCallsTitle =
    preset === 'custom'
      ? 'tool calls (custom total)'
      : `tool calls (${preset} total)`

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
      <div className="range-controls">
        {(['15m', '1h', '6h', '24h', '7d', 'custom'] as const).map((key) => (
          <button
            key={key}
            className={`tab-trigger range-button ${preset === key ? 'is-active' : ''}`}
            onClick={() => setPreset(key)}
            aria-pressed={preset === key}
          >
            {key}
          </button>
        ))}
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
      <Tabs className="tabs" defaultValue="now">
        <TabsList>
          <TabsTrigger value="now">Now</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
          <TabsTrigger value="logs">Logs</TabsTrigger>
        </TabsList>

        <TabsContent value="now">
          <div className="grid grid-3">
            <Card>
              <p className="title">{toolCallsTitle}</p>
              <p className="value">{totalToolCallsInRange}</p>
            </Card>
            <Card>
              <p className="title">error rate</p>
              <p className="value">
                {((current?.error_rate ?? 0) * 100).toFixed(1)}%
              </p>
            </Card>
            <Card>
              <p className="title">latest emotion / intensity</p>
              <p className="value">
                {current?.latest?.emotion_primary ?? 'n/a'}
              </p>
              <Badge>
                {(current?.latest?.emotion_intensity ?? 0).toFixed(2)}
              </Badge>
            </Card>
          </div>
          <Card>
            <h3>Realtime intensity trend</h3>
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
            <h3>Event feed</h3>
            <p className="helper-text">Timestamps: {clientTimeZone}</p>
            <div className="feed">
              {feed.map((item) => (
                <div className="feed-item" key={item.ts}>
                  {formatTimestamp(item.ts, timestampFormatter)} / time_phase=
                  {item.value}
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
