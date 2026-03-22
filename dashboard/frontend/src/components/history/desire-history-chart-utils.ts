import type { ChartConfig } from '@/components/ui/chart'

export const DYNAMIC_DESIRE_COLORS = [
  'var(--color-chart-1)',
  'var(--color-chart-2)',
  'var(--color-chart-3)',
  'var(--color-chart-4)',
  'var(--color-chart-5)',
  'var(--color-chart-6)',
  'var(--color-chart-7)',
  'var(--color-chart-8)',
  'var(--color-chart-9)',
]

export const resolveDesireSeriesColor = (
  key: string,
  chartConfig: ChartConfig,
  index: number,
) =>
  chartConfig[key]?.color ??
  DYNAMIC_DESIRE_COLORS[index % DYNAMIC_DESIRE_COLORS.length]
