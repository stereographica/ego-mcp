import { useMemo, useState } from 'react'
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
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from '@/components/ui/chart'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  DESIRE_CHART_CONFIG,
  DESIRE_METRIC_KEYS,
  formatMetricLabel,
} from '@/constants'
import { useTimestampFormatter } from '@/hooks/use-timestamp-formatter'
import type { HistoryMarker } from '@/types'
import {
  DYNAMIC_DESIRE_COLORS,
  resolveDesireSeriesColor,
} from '@/components/history/desire-history-chart-utils'

type DesireHistoryChartProps = {
  desireChartData: Record<string, number | string>[]
  desireKeys: string[]
  markers?: HistoryMarker[]
}

export const DesireHistoryChart = ({
  desireChartData,
  desireKeys,
  markers = [],
}: DesireHistoryChartProps) => {
  const { formatTs } = useTimestampFormatter()
  const [hiddenKeys, setHiddenKeys] = useState<Set<string>>(new Set())
  const { chartConfig, dynamicKeys } = useMemo(() => {
    const fixedKeySet = new Set<string>(DESIRE_METRIC_KEYS)
    const dynamicKeys = desireKeys.filter((key) => !fixedKeySet.has(key))
    const dynamicConfig = Object.fromEntries(
      dynamicKeys.map((key, index) => [
        key,
        {
          label: formatMetricLabel(key),
          color: DYNAMIC_DESIRE_COLORS[index % DYNAMIC_DESIRE_COLORS.length],
        },
      ]),
    )
    return {
      chartConfig: {
        ...DESIRE_CHART_CONFIG,
        ...dynamicConfig,
      },
      dynamicKeys,
    }
  }, [desireKeys])
  const desireMarkers = useMemo(
    () =>
      markers.filter(
        (marker) =>
          marker.kind === 'impulse' ||
          marker.kind === 'emergent' ||
          marker.kind === 'proust',
      ),
    [markers],
  )
  const allSeriesKeys = useMemo(
    () => [...DESIRE_METRIC_KEYS, ...dynamicKeys],
    [dynamicKeys],
  )
  const visibleKeys = useMemo(
    () => allSeriesKeys.filter((key) => !hiddenKeys.has(key)),
    [allSeriesKeys, hiddenKeys],
  )

  const toggleSeries = (key: string) => {
    setHiddenKeys((current) => {
      const next = new Set(current)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Desire parameter history</CardTitle>
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig} className="h-[340px] w-full">
          <LineChart data={desireChartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="ts" hide />
            <YAxis domain={[0, 1]} />
            <ChartTooltip
              content={
                <ChartTooltipContent
                  labelFormatter={formatTs}
                  showAllSeries
                  missingValueLabel="-"
                  visibleKeys={visibleKeys}
                />
              }
            />
            <ChartLegend
              content={<ChartLegendContent onSeriesToggle={toggleSeries} />}
            />
            {desireMarkers.map((marker) => (
              <ReferenceLine
                key={`${marker.kind}-${marker.ts}-${marker.desire_key ?? marker.detail ?? ''}`}
                x={marker.ts}
                stroke={
                  marker.kind === 'impulse'
                    ? 'var(--color-chart-1)'
                    : marker.kind === 'proust'
                      ? 'var(--color-chart-3)'
                      : 'var(--color-chart-4)'
                }
                strokeDasharray="3 3"
                ifOverflow="extendDomain"
                label={{
                  value:
                    marker.kind === 'impulse'
                      ? `Impulse: ${marker.detail ?? marker.desire_key ?? ''}`
                      : marker.kind === 'proust'
                        ? `Proust: ${marker.detail ?? marker.memory_id ?? ''}`
                        : (marker.detail ?? 'Emergent'),
                  position: 'top',
                  fill: 'var(--color-muted-foreground)',
                  fontSize: 10,
                }}
              />
            ))}
            {DESIRE_METRIC_KEYS.map((key) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                stroke={resolveDesireSeriesColor(key, chartConfig, 0)}
                dot={false}
                connectNulls
                hide={hiddenKeys.has(key)}
              />
            ))}
            {dynamicKeys.map((key, index) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                stroke={resolveDesireSeriesColor(key, chartConfig, index)}
                strokeWidth={2}
                strokeDasharray="4 2"
                dot={false}
                connectNulls
                hide={hiddenKeys.has(key)}
              />
            ))}
          </LineChart>
        </ChartContainer>
        {desireChartData.length === 0 && (
          <p className="text-muted-foreground mt-2 text-xs">
            No desire metric data in selected range.
          </p>
        )}
      </CardContent>
    </Card>
  )
}
