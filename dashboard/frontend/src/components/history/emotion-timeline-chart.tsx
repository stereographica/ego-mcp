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
import {
  buildEmotionAxis,
  normalizeEmotion,
} from '@/components/history/emotion-timeline-utils'
import { useTimestampFormatter } from '@/hooks/use-timestamp-formatter'
import type { EmotionTrendPoint } from '@/types'
import { useMemo } from 'react'

type EmotionTimelineChartProps = {
  points: EmotionTrendPoint[]
}

const config: ChartConfig = {
  emotion_level: { label: 'emotion', color: 'var(--color-chart-5)' },
}

export const EmotionTimelineChart = ({ points }: EmotionTimelineChartProps) => {
  const { formatTs } = useTimestampFormatter()
  const { chartData, ticks, levelToEmotion, maxLevel } = useMemo(() => {
    const axis = buildEmotionAxis(points)
    const nextData = points.map((point) => {
      const emotion =
        typeof point.emotion_primary === 'string'
          ? normalizeEmotion(point.emotion_primary)
          : undefined
      return {
        ...point,
        emotion_primary: emotion,
        emotion_level:
          typeof emotion === 'string'
            ? (axis.emotionToLevel.get(emotion) ?? null)
            : null,
      }
    })
    const maxAbsTick = axis.ticks.reduce(
      (max, tick) => Math.max(max, Math.abs(tick)),
      0,
    )
    return {
      chartData: nextData,
      ticks: axis.ticks,
      levelToEmotion: axis.levelToEmotion,
      maxLevel: Math.max(1, maxAbsTick),
    }
  }, [points])

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
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="ts" hide />
            <YAxis
              domain={[-maxLevel, maxLevel]}
              ticks={ticks}
              allowDecimals={false}
              tickFormatter={(tickValue) =>
                levelToEmotion.get(Number(tickValue)) ?? ''
              }
            />
            <ReferenceLine y={0} stroke="#ccc" strokeDasharray="4 4" />
            <ChartTooltip
              content={
                <ChartTooltipContent labelFormatter={formatTooltipLabel} />
              }
            />
            <Line
              type="monotone"
              dataKey="emotion_level"
              stroke="var(--color-emotion_level)"
              dot={false}
            />
          </LineChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
