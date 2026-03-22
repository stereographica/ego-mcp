import { resolveDesireSeriesColor } from '@/components/history/desire-history-chart-utils'
import type { ChartConfig } from '@/components/ui/chart'

describe('resolveDesireSeriesColor', () => {
  it('uses chart colors instead of interpolating raw dynamic keys into css vars', () => {
    const color = resolveDesireSeriesColor('novelty', {}, 0)

    expect(color).toBe('var(--color-chart-1)')
    expect(color).not.toContain('novelty')
  })

  it('prefers explicit chart config colors when present', () => {
    const color = resolveDesireSeriesColor(
      'novelty',
      { novelty: { color: 'var(--color-chart-5)' } } as ChartConfig,
      0,
    )

    expect(color).toBe('var(--color-chart-5)')
  })
})
