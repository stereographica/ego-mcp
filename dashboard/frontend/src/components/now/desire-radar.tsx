import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
} from 'recharts'

import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from '@/components/ui/chart'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  DESIRE_CHART_CONFIG,
  DESIRE_METRIC_KEYS,
  formatMetricLabel,
} from '@/constants'
import type { CurrentResponse } from '@/types'

type DesireRadarProps = {
  current: CurrentResponse | null
}

export const DesireRadar = ({ current }: DesireRadarProps) => {
  const desires = current?.latest_desires ?? {}
  const data = DESIRE_METRIC_KEYS.map((key) => ({
    name: formatMetricLabel(key),
    value: desires[key] ?? 0,
  }))

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Desire parameters</CardTitle>
      </CardHeader>
      <CardContent>
        <ChartContainer
          config={DESIRE_CHART_CONFIG}
          className="mx-auto aspect-square max-h-[300px]"
        >
          <RadarChart data={data}>
            <ChartTooltip content={<ChartTooltipContent />} />
            <PolarAngleAxis
              dataKey="name"
              tick={{ fontSize: 10, fill: 'var(--color-muted-foreground)' }}
            />
            <PolarRadiusAxis domain={[0, 1]} tick={false} axisLine={false} />
            <PolarGrid stroke="var(--color-border)" />
            <Radar
              dataKey="value"
              fill="var(--color-chart-2)"
              fillOpacity={0.6}
              stroke="var(--color-chart-2)"
            />
          </RadarChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
