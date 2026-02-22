import { useEffect, useMemo, useState } from 'react'
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

const App = () => {
  const [preset, setPreset] = useState<TimeRangePreset>('1h')
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo] = useState('')
  const [logLevel, setLogLevel] = useState('ALL')
  const [loggerFilter, setLoggerFilter] = useState('')
  const [autoScroll, setAutoScroll] = useState(true)

  const [current, setCurrent] = useState<CurrentResponse | null>(null)
  const [intensity, setIntensity] = useState<SeriesPoint[]>([])
  const [usage, setUsage] = useState<UsagePoint[]>([])
  const [timeline, setTimeline] = useState<StringPoint[]>([])
  const [heatmap, setHeatmap] = useState<HeatmapPoint[]>([])
  const [logs, setLogs] = useState<LogPoint[]>([])

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

  const feed = useMemo(
    () =>
      timeline
        .slice(-8)
        .map((point) => `${point.ts} / time_phase=${point.value}`),
    [timeline],
  )

  useEffect(() => {
    if (autoScroll) {
      const el = document.getElementById('log-feed')
      if (el) el.scrollTop = el.scrollHeight
    }
  }, [logs, autoScroll])

  return (
    <main className="container">
      <h1>ego-mcp Dashboard</h1>
      <div
        style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}
      >
        {(['15m', '1h', '6h', '24h', '7d', 'custom'] as const).map((key) => (
          <button
            key={key}
            className="tab-trigger"
            onClick={() => setPreset(key)}
          >
            {key}
          </button>
        ))}
        {preset === 'custom' && (
          <>
            <input
              type="datetime-local"
              value={customFrom}
              onChange={(e) => setCustomFrom(e.target.value)}
            />
            <input
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
              <p className="title">tool calls / min</p>
              <p className="value">{current?.tool_calls_per_min ?? 0}</p>
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
                <Tooltip />
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
            <div className="feed">
              {feed.map((item) => (
                <div className="feed-item" key={item}>
                  {item}
                </div>
              ))}
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="history">
          <Card>
            <h3>Tool usage history</h3>
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={usage}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="ts" hide />
                <YAxis />
                <Tooltip />
                <Legend />
                <Area
                  type="monotone"
                  dataKey="feel_desires"
                  stackId="1"
                  stroke="#334155"
                  fill="#94a3b8"
                />
                <Area
                  type="monotone"
                  dataKey="remember"
                  stackId="1"
                  stroke="#1e293b"
                  fill="#475569"
                />
              </AreaChart>
            </ResponsiveContainer>
          </Card>
          <Card>
            <h3>time_phase timeline + heatmap</h3>
            <div className="feed">
              {timeline.map((item) => (
                <div key={item.ts} className="feed-item">
                  <strong>{item.ts}</strong> <Badge>{item.value}</Badge>
                </div>
              ))}
              {heatmap.map((item) => (
                <div key={`heat-${item.ts}`} className="feed-item">
                  <strong>{item.ts}</strong> {JSON.stringify(item.counts)}
                </div>
              ))}
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="logs">
          <Card>
            <h3>Live tail</h3>
            <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
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
            <div className="feed" id="log-feed">
              {logs.map((item) => (
                <div
                  key={`log-${item.ts}-${item.message}`}
                  className="feed-item"
                >
                  [{item.level}] {item.logger}{' '}
                  {item.private ? 'REDACTED' : item.message}
                </div>
              ))}
            </div>
          </Card>
        </TabsContent>
      </Tabs>
    </main>
  )
}

export default App
