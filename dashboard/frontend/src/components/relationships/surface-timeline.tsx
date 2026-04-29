import { useMemo } from 'react'
import {
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  Tooltip,
} from 'recharts'

import { ChartContainer, type ChartConfig } from '@/components/ui/chart'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { SurfaceTimelinePoint, PersonOverview } from '@/types'

type SurfaceTimelineProps = {
  points: SurfaceTimelinePoint[]
  isLoading: boolean
  persons: PersonOverview[]
}

const RESONANT_COLOR = '#3b82f6'
const INVOLUNTARY_COLOR = '#f59e0b'

const buildPersonNameMap = (persons: PersonOverview[]): Map<string, string> => {
  const map = new Map<string, string>()
  for (const p of persons) {
    map.set(p.person_id, p.name || p.person_id)
  }
  return map
}

const formatTooltipLabel = (ts: string): string => {
  try {
    const d = new Date(ts)
    return d.toLocaleString()
  } catch {
    return ts
  }
}

const chartConfig: ChartConfig = {
  resonant: {
    label: 'Resonant',
    color: RESONANT_COLOR,
  },
  involuntary: {
    label: 'Involuntary',
    color: INVOLUNTARY_COLOR,
  },
}

export const SurfaceTimeline = ({
  points,
  isLoading,
  persons,
}: SurfaceTimelineProps) => {
  const personNameMap = useMemo(() => buildPersonNameMap(persons), [persons])

  const data = useMemo(() => {
    const sorted = [...points].sort((a, b) => a.ts.localeCompare(b.ts))
    return sorted.map((pt) => ({
      ts: new Date(pt.ts).getTime(),
      tsLabel: pt.ts,
      person_id: pt.person_id,
      display_name: personNameMap.get(pt.person_id) || pt.person_id,
      surface_type: pt.surface_type,
      fill: pt.surface_type === 'resonant' ? RESONANT_COLOR : INVOLUNTARY_COLOR,
    }))
  }, [points, personNameMap])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-[280px]">
        <p className="text-muted-foreground text-sm">Loading...</p>
      </div>
    )
  }

  if (points.length === 0) {
    return (
      <p className="text-muted-foreground text-sm py-8 text-center">
        No surface events recorded yet. Surface events appear when using{' '}
        <code className="text-xs bg-muted px-1 py-0.5 rounded">recall</code>.
      </p>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Surface timeline</CardTitle>
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig} className="h-[280px] w-full">
          <ResponsiveContainer>
            <ScatterChart>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                type="number"
                dataKey="ts"
                name="time"
                tickFormatter={(ts) =>
                  formatTooltipLabel(new Date(ts).toISOString())
                }
                scale="time"
              />
              <YAxis
                dataKey="display_name"
                name="person"
                type="category"
                tick={{ fontSize: 12 }}
              />
              <Tooltip
                cursor={{ strokeDasharray: '3 3' }}
                formatter={(value: string, name: string) => {
                  if (name === 'ts') {
                    return [
                      formatTooltipLabel(new Date(Number(value)).toISOString()),
                      'time',
                    ]
                  }
                  return [value, name]
                }}
                labelFormatter={() => ''}
              />
              <Scatter data={data} fill="#8884d8" isAnimationActive={false}>
                {data.map((entry, index) => (
                  <Cell key={index} fill={entry.fill} />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
