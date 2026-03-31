import { useMemo } from 'react'
import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
} from 'recharts'

import { Badge } from '@/components/ui/badge'
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from '@/components/ui/chart'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { buildDesireRadarSeriesData } from '@/desires'
import type { CurrentResponse, DesireCatalogItem } from '@/types'

type DesireRadarProps = {
  current: CurrentResponse | null
  desireCatalog: DesireCatalogItem[]
}

export const DesireRadar = ({ current, desireCatalog }: DesireRadarProps) => {
  const {
    chartConfig,
    chartData,
    hasDynamicDesires,
    boostedDesire,
    boostAmount,
  } = useMemo(
    () => buildDesireRadarSeriesData(desireCatalog, current),
    [current, desireCatalog],
  )

  return (
    <Card>
      <CardHeader className="space-y-2">
        <CardTitle className="text-sm">Desire parameters</CardTitle>
        <div className="flex flex-wrap gap-2 text-xs">
          {hasDynamicDesires ? (
            <Badge variant="outline">dynamic axes</Badge>
          ) : null}
          {boostedDesire ? (
            <Badge variant="secondary">
              impulse boost {boostedDesire}
              {typeof boostAmount === 'number'
                ? ` +${boostAmount.toFixed(2)}`
                : ''}
            </Badge>
          ) : null}
        </div>
      </CardHeader>
      <CardContent>
        <ChartContainer
          config={chartConfig}
          className="mx-auto aspect-square max-h-[320px]"
        >
          <RadarChart data={chartData}>
            <ChartTooltip content={<ChartTooltipContent />} />
            <PolarAngleAxis
              dataKey="name"
              tick={{ fontSize: 10, fill: 'var(--color-muted-foreground)' }}
            />
            <PolarRadiusAxis domain={[0, 1]} tick={false} axisLine={false} />
            <PolarGrid stroke="var(--color-border)" />
            <Radar
              dataKey="fixed_desires"
              fill="var(--color-fixed_desires)"
              fillOpacity={0.22}
              stroke="var(--color-fixed_desires)"
            />
            <Radar
              dataKey="dynamic_desires"
              fill="var(--color-dynamic_desires)"
              fillOpacity={0.2}
              stroke="var(--color-dynamic_desires)"
              strokeDasharray="4 2"
            />
            <Radar
              dataKey="boosted_desire"
              fill="var(--color-boosted_desire)"
              fillOpacity={0.45}
              stroke="var(--color-boosted_desire)"
              strokeWidth={2}
            />
          </RadarChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
