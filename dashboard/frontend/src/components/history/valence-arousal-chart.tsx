import { CartesianGrid, Line, LineChart, XAxis, YAxis } from 'recharts'

import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useTimestampFormatter } from '@/hooks/use-timestamp-formatter'
import type { SeriesPoint } from '@/types'
import { useMemo } from 'react'

type ValenceArousalChartProps = {
  valence: SeriesPoint[]
  arousal: SeriesPoint[]
}

const config: ChartConfig = {
  valence: { label: 'valence', color: 'var(--color-chart-2)' },
  arousal: { label: 'arousal', color: 'var(--color-chart-4)' },
}

export const ValenceArousalChart = ({
  valence,
  arousal,
}: ValenceArousalChartProps) => {
  const { formatTs } = useTimestampFormatter()

  const data = useMemo(() => {
    const byTs = new Map<
      string,
      { ts: string; valence?: number; arousal?: number }
    >()
    for (const p of valence) {
      const row = byTs.get(p.ts) ?? { ts: p.ts }
      row.valence = p.value
      byTs.set(p.ts, row)
    }
    for (const p of arousal) {
      const row = byTs.get(p.ts) ?? { ts: p.ts }
      row.arousal = p.value
      byTs.set(p.ts, row)
    }
    return Array.from(byTs.values()).sort((a, b) => a.ts.localeCompare(b.ts))
  }, [valence, arousal])

  if (data.length === 0) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Valence / Arousal history</CardTitle>
      </CardHeader>
      <CardContent>
        <ChartContainer config={config} className="h-[260px] w-full">
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="ts" hide />
            <YAxis domain={[-1, 1]} />
            <ChartTooltip
              content={<ChartTooltipContent labelFormatter={formatTs} />}
            />
            <ChartLegend content={<ChartLegendContent />} />
            <Line
              type="monotone"
              dataKey="valence"
              stroke="var(--color-valence)"
              dot={false}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="arousal"
              stroke="var(--color-arousal)"
              dot={false}
              connectNulls
            />
          </LineChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
