import { CartesianGrid, Line, LineChart, XAxis, YAxis } from 'recharts'

import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useTimestampFormatter } from '@/hooks/use-timestamp-formatter'
import type { SeriesPoint } from '@/types'

type IntensityChartProps = {
  intensity: SeriesPoint[]
}

const config: ChartConfig = {
  value: { label: 'intensity', color: 'var(--color-primary)' },
}

export const IntensityChart = ({ intensity }: IntensityChartProps) => {
  const { formatTs } = useTimestampFormatter()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Intensity history</CardTitle>
      </CardHeader>
      <CardContent>
        <ChartContainer config={config} className="h-[260px] w-full">
          <LineChart data={intensity}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="ts" hide />
            <YAxis domain={[0, 1]} />
            <ChartTooltip
              content={<ChartTooltipContent labelFormatter={formatTs} />}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke="var(--color-value)"
              dot={false}
            />
          </LineChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
