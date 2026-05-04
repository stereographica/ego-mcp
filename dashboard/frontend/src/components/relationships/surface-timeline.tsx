import { useMemo } from 'react'
import {
  CartesianGrid,
  Cell,
  ScatterChart,
  Scatter,
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
  buildPersonNameMap,
  buildSurfaceTimelineData,
  formatSurfaceType,
  type SurfaceTimelineChartPoint,
} from '@/components/relationships/surface-timeline-utils'
import { formatTooltipTimestampLabel } from '@/components/relationships/tooltip-utils'
import { useTimestampFormatter } from '@/hooks/use-timestamp-formatter'
import type { SurfaceTimelinePoint, PersonOverview } from '@/types'

type SurfaceTimelineProps = {
  points: SurfaceTimelinePoint[]
  isLoading: boolean
  persons: PersonOverview[]
}

const chartConfig: ChartConfig = {
  display_name: { label: 'Person' },
  surface_type: { label: 'Surface type' },
}

export const SurfaceTimeline = ({
  points,
  isLoading,
  persons,
}: SurfaceTimelineProps) => {
  const { formatTs } = useTimestampFormatter()
  const personNameMap = useMemo(() => buildPersonNameMap(persons), [persons])
  const data = useMemo(
    () => buildSurfaceTimelineData(points, personNameMap),
    [points, personNameMap],
  )

  return (
    <Card className="min-w-0 overflow-hidden">
      <CardHeader>
        <CardTitle className="text-sm">Surface timeline</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex h-[280px] items-center justify-center">
            <p className="text-muted-foreground text-sm">Loading...</p>
          </div>
        ) : points.length === 0 ? (
          <p className="text-muted-foreground py-8 text-center text-sm">
            No surface events recorded yet. Surface events appear when using{' '}
            <code className="bg-muted rounded px-1 py-0.5 text-xs">recall</code>
            .
          </p>
        ) : (
          <ChartContainer config={chartConfig} className="h-[280px] w-full">
            <ScatterChart margin={{ top: 8, right: 12, bottom: 0, left: 12 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                type="number"
                dataKey="ts"
                name="time"
                tickFormatter={(ts) =>
                  formatTs(new Date(Number(ts)).toISOString())
                }
                scale="time"
              />
              <YAxis
                type="category"
                dataKey="display_name"
                name="person"
                width={96}
                interval={0}
                tick={{ fontSize: 12 }}
              />
              <ChartTooltip
                cursor={{ strokeDasharray: '3 3' }}
                content={({ active, payload }) => {
                  const point = payload?.[0]?.payload as
                    | SurfaceTimelineChartPoint
                    | undefined

                  if (!active || !point) {
                    return null
                  }

                  return (
                    <ChartTooltipContent
                      active={active}
                      label={point.tsLabel}
                      labelFormatter={(label) =>
                        formatTooltipTimestampLabel(label, formatTs)
                      }
                      payload={[
                        {
                          name: 'display_name',
                          dataKey: 'display_name',
                          value: point.display_name,
                          color: point.fill,
                          payload: point,
                        },
                        {
                          name: 'surface_type',
                          dataKey: 'surface_type',
                          value: formatSurfaceType(point.surface_type),
                          color: point.fill,
                          payload: point,
                        },
                      ]}
                    />
                  )
                }}
              />
              <Scatter data={data} isAnimationActive={false}>
                {data.map((entry, index) => (
                  <Cell key={index} fill={entry.fill} />
                ))}
              </Scatter>
            </ScatterChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  )
}
