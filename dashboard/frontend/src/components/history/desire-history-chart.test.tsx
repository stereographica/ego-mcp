import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'

import { DesireHistoryChart } from '@/components/history/desire-history-chart'
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

describe('DesireHistoryChart', () => {
  it('shows an empty-state message when there is no desire data in range', () => {
    const consoleErrorSpy = vi
      .spyOn(console, 'error')
      .mockImplementation(() => {})
    const consoleWarnSpy = vi
      .spyOn(console, 'warn')
      .mockImplementation(() => {})

    render(
      <DesireHistoryChart
        desireChartData={[]}
        desireKeys={[]}
        desireCatalog={[
          {
            id: 'information_hunger',
            display_name: 'information hunger',
            maslow_level: 1,
          },
        ]}
        markers={[
          {
            ts: '2026-01-01T12:00:00Z',
            kind: 'emergent',
            label: 'Emergent desire',
            detail: 'novelty',
            desire_key: 'novelty',
          },
        ]}
      />,
    )

    expect(screen.getByText('Desire parameter history')).toBeInTheDocument()
    expect(
      screen.getByText('No desire metric data in selected range.'),
    ).toBeInTheDocument()
    expect(consoleErrorSpy).not.toHaveBeenCalled()
    expect(consoleWarnSpy).not.toHaveBeenCalled()

    consoleErrorSpy.mockRestore()
    consoleWarnSpy.mockRestore()
  })
})
