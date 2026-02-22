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
  fetchTimeline,
  fetchUsage,
} from './api'
import { Badge } from './components/ui/badge'
import { Card } from './components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from './components/ui/tabs'
import type {
  CurrentResponse,
  HeatmapPoint,
  SeriesPoint,
  StringPoint,
  UsagePoint,
} from './types'

const App = () => {
  const [current, setCurrent] = useState<CurrentResponse | null>(null)
  const [intensity, setIntensity] = useState<SeriesPoint[]>([])
  const [usage, setUsage] = useState<UsagePoint[]>([])
  const [timeline, setTimeline] = useState<StringPoint[]>([])
  const [heatmap, setHeatmap] = useState<HeatmapPoint[]>([])

  useEffect(() => {
    const load = async () => {
      const [c, i, u, t, h] = await Promise.all([
        fetchCurrent(),
        fetchIntensity(),
        fetchUsage(),
        fetchTimeline(),
        fetchHeatmap(),
      ])
      setCurrent(c)
      setIntensity(i)
      setUsage(u)
      setTimeline(t)
      setHeatmap(h)
    }
    void load()
    const timer = setInterval(load, 2000)
    return () => clearInterval(timer)
  }, [])

  const feed = useMemo(
    () =>
      timeline
        .slice(-8)
        .map((point) => `${point.ts} / time_phase=${point.value}`),
    [timeline],
  )

  return (
    <main className="container">
      <h1>ego-mcp Dashboard</h1>
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
            <h3>time_phase heatmap (table)</h3>
            <div className="feed">
              {heatmap.map((item) => (
                <div key={item.ts} className="feed-item">
                  <strong>{item.ts}</strong> {JSON.stringify(item.counts)}
                </div>
              ))}
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="logs">
          <Card>
            <h3>Live tail (masked)</h3>
            <div className="feed">
              {feed.map((item) => (
                <div key={`log-${item}`} className="feed-item">
                  {item.includes('private') ? 'REDACTED' : item}
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
