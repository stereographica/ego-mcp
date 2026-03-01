import { useMemo } from 'react'
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from 'recharts'

import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { aggregateEmotionCounts } from '@/components/history/emotion-distribution-utils'
import type { HeatmapPoint } from '@/types'

type EmotionDistributionChartProps = {
  heatmapData: HeatmapPoint[]
}

const config: ChartConfig = {
  count: { label: 'count', color: 'var(--color-chart-2)' },
}

export const EmotionDistributionChart = ({
  heatmapData,
}: EmotionDistributionChartProps) => {
  const data = useMemo(() => aggregateEmotionCounts(heatmapData), [heatmapData])

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Emotion distribution</CardTitle>
      </CardHeader>
      <CardContent>
        <ChartContainer config={config} className="h-[260px] w-full">
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="emotion" />
            <YAxis allowDecimals={false} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <Bar dataKey="count" fill="var(--color-count)" radius={4} />
          </BarChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
