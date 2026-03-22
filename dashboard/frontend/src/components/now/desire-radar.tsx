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
import {
  DESIRE_CHART_CONFIG,
  DESIRE_METRIC_KEYS,
  formatMetricLabel,
} from '@/constants'
import type { CurrentResponse } from '@/types'

type DesireRadarProps = {
  current: CurrentResponse | null
}

const DYNAMIC_COLORS = [
  'var(--color-chart-4)',
  'var(--color-chart-5)',
  'var(--color-chart-6)',
  'var(--color-chart-7)',
  'var(--color-chart-8)',
  'var(--color-chart-9)',
]

export const DesireRadar = ({ current }: DesireRadarProps) => {
  const boostedDesire =
    current?.latest?.string_metrics?.impulse_boosted_desire ?? undefined
  const boostAmount = current?.latest?.numeric_metrics?.impulse_boost_amount

  const { chartConfig, chartData, hasDynamicDesires } = useMemo(() => {
    const fixedDesires = current?.latest_desires ?? {}
    const emergentDesires = current?.latest_emergent_desires ?? {}
    const fixedKeySet = new Set<string>(DESIRE_METRIC_KEYS)
    const dynamicKeys = Object.keys(emergentDesires)
      .filter((key) => !fixedKeySet.has(key))
      .sort()
    const axisKeys = [...DESIRE_METRIC_KEYS, ...dynamicKeys]
    const dynamicConfig = Object.fromEntries(
      dynamicKeys.map((key, index) => [
        key,
        {
          label: formatMetricLabel(key),
          color: DYNAMIC_COLORS[index % DYNAMIC_COLORS.length],
        },
      ]),
    )
    const combinedConfig = {
      ...DESIRE_CHART_CONFIG,
      ...dynamicConfig,
      fixed_desires: {
        label: 'fixed desires',
        color: 'var(--color-chart-2)',
      },
      dynamic_desires: {
        label: 'dynamic desires',
        color: 'var(--color-chart-4)',
      },
      boosted_desire: {
        label: 'impulse boost',
        color: 'var(--color-chart-1)',
      },
    }
    const data = axisKeys.map((key) => ({
      name: formatMetricLabel(key),
      fixed_desires: fixedDesires[key] ?? 0,
      dynamic_desires: emergentDesires[key] ?? 0,
      boosted_desire:
        key === boostedDesire
          ? (emergentDesires[key] ?? fixedDesires[key] ?? 0)
          : 0,
    }))
    return {
      chartConfig: combinedConfig,
      chartData: data,
      hasDynamicDesires: dynamicKeys.length > 0,
    }
  }, [boostedDesire, current])

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
