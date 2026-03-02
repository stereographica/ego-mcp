import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  XAxis,
  YAxis,
} from 'recharts'

import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useTimestampFormatter } from '@/hooks/use-timestamp-formatter'
import type { EmotionTrendPoint } from '@/types'

type EmotionTimelineChartProps = {
  points: EmotionTrendPoint[]
}

const config: ChartConfig = {
  value: { label: 'emotion polarity', color: 'var(--color-chart-5)' },
}

const formatPolarityTick = (value: number) => {
  if (value === 1) return 'positive'
  if (value === 0) return 'neutral'
  if (value === -1) return 'negative'
  return String(value)
}

export const EmotionTimelineChart = ({ points }: EmotionTimelineChartProps) => {
  const { formatTs } = useTimestampFormatter()

  const formatTooltipLabel = (
    label: unknown,
    payload: Array<{ payload?: { emotion_primary?: string } }> | undefined,
  ) => {
    const labelText =
      typeof label === 'string' ? formatTs(label) : String(label ?? '')
    const emotion = payload?.[0]?.payload?.emotion_primary
    if (typeof emotion === 'string' && emotion.length > 0) {
      return `${labelText} — ${emotion}`
    }
    return labelText
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Emotion trend</CardTitle>
      </CardHeader>
      <CardContent>
        <ChartContainer config={config} className="h-[260px] w-full">
          <LineChart data={points}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="ts" hide />
            <YAxis
              domain={[-1, 1]}
              ticks={[-1, 0, 1]}
              tickFormatter={formatPolarityTick}
            />
            <ReferenceLine y={0} stroke="#ccc" strokeDasharray="4 4" />
            <ChartTooltip
              content={
                <ChartTooltipContent labelFormatter={formatTooltipLabel} />
              }
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke="var(--color-value)"
              dot={false}
              connectNulls
            />
          </LineChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
