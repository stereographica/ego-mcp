import { CartesianGrid, Line, LineChart, XAxis, YAxis } from 'recharts'

import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from '@/components/ui/chart'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { DESIRE_CHART_CONFIG, DESIRE_METRIC_KEYS } from '@/constants'
import { useTimestampFormatter } from '@/hooks/use-timestamp-formatter'

type DesireHistoryChartProps = {
  desireChartData: Record<string, number | string>[]
}

export const DesireHistoryChart = ({
  desireChartData,
}: DesireHistoryChartProps) => {
  const { formatTs } = useTimestampFormatter()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Desire parameter history</CardTitle>
      </CardHeader>
      <CardContent>
        <ChartContainer
          config={DESIRE_CHART_CONFIG}
          className="h-[340px] w-full"
        >
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
                />
              }
            />
            <ChartLegend content={<ChartLegendContent />} />
            {DESIRE_METRIC_KEYS.map((key) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                stroke={`var(--color-${key})`}
                dot={false}
                connectNulls
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
