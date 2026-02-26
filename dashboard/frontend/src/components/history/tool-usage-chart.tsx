import { useMemo } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceArea,
  XAxis,
  YAxis,
} from 'recharts'

import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { TOOL_CHART_COLORS } from '@/constants'
import { useTimestampFormatter } from '@/hooks/use-timestamp-formatter'
import type { StringPoint, UsagePoint } from '@/types'

type ToolUsageChartProps = {
  usage: UsagePoint[]
  toolSeriesKeys: string[]
  timeline: StringPoint[]
}

const PHASE_COLORS: Record<string, string> = {
  late_night: 'oklch(0.30 0.06 280 / 0.18)',
  early_morning: 'oklch(0.45 0.08 60 / 0.15)',
  morning: 'oklch(0.55 0.10 90 / 0.12)',
  afternoon: 'oklch(0.55 0.08 60 / 0.10)',
  evening: 'oklch(0.45 0.10 30 / 0.12)',
  night: 'oklch(0.30 0.08 260 / 0.15)',
}

type PhaseSpan = { x1: string; x2: string; phase: string }

export const ToolUsageChart = ({
  usage,
  toolSeriesKeys,
  timeline,
}: ToolUsageChartProps) => {
  const { formatTs } = useTimestampFormatter()

  const config: ChartConfig = Object.fromEntries(
    toolSeriesKeys.map((key, i) => [
      key,
      {
        label: key.replaceAll('_', ' '),
        color: TOOL_CHART_COLORS[i % TOOL_CHART_COLORS.length],
      },
    ]),
  )

  const phaseSpans = useMemo<PhaseSpan[]>(() => {
    if (timeline.length === 0) return []
    const spans: PhaseSpan[] = []
    let current = { phase: timeline[0].value, start: timeline[0].ts }
    for (let i = 1; i < timeline.length; i++) {
      const pt = timeline[i]
      if (pt.value !== current.phase) {
        spans.push({ x1: current.start, x2: pt.ts, phase: current.phase })
        current = { phase: pt.value, start: pt.ts }
      }
    }
    spans.push({
      x1: current.start,
      x2: timeline[timeline.length - 1].ts,
      phase: current.phase,
    })
    return spans
  }, [timeline])

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Tool usage history</CardTitle>
        {phaseSpans.length > 0 && (
          <p className="text-muted-foreground text-xs">
            Background bands show time_phase (cognitive phase)
          </p>
        )}
      </CardHeader>
      <CardContent>
        <ChartContainer config={config} className="h-[280px] w-full">
          <AreaChart data={usage}>
            {phaseSpans.map((span, i) => (
              <ReferenceArea
                key={`phase-${i}`}
                x1={span.x1}
                x2={span.x2}
                fill={PHASE_COLORS[span.phase] ?? 'transparent'}
                fillOpacity={1}
                ifOverflow="hidden"
              />
            ))}
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="ts" hide />
            <YAxis />
            <ChartTooltip
              content={
                <ChartTooltipContent labelFormatter={formatTs} showAllSeries />
              }
            />
            <ChartLegend content={<ChartLegendContent />} />
            {toolSeriesKeys.map((toolName) => (
              <Area
                key={toolName}
                type="monotone"
                dataKey={toolName}
                stackId="1"
                stroke={`var(--color-${toolName})`}
                fill={`var(--color-${toolName})`}
                fillOpacity={0.4}
              />
            ))}
          </AreaChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
