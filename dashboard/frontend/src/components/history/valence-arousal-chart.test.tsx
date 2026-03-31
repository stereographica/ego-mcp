import { fireEvent, render, screen } from '@testing-library/react'

import { ValenceArousalChart } from '@/components/history/valence-arousal-chart'

describe('ValenceArousalChart', () => {
  it('toggles a series from the legend', () => {
    const { container } = render(
      <ValenceArousalChart
        valence={[
          { ts: '2026-01-01T12:00:00Z', value: 0.2 },
          { ts: '2026-01-01T12:05:00Z', value: 0.4 },
        ]}
        arousal={[
          { ts: '2026-01-01T12:00:00Z', value: -0.3 },
          { ts: '2026-01-01T12:05:00Z', value: 0.1 },
        ]}
      />,
    )

    expect(container.querySelectorAll('.recharts-line-curve')).toHaveLength(2)

    const valenceLegend = screen.getByRole('button', { name: 'valence' })
    expect(valenceLegend).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(valenceLegend)

    expect(valenceLegend).toHaveAttribute('aria-pressed', 'false')
    expect(container.querySelectorAll('.recharts-line-curve')).toHaveLength(1)

    fireEvent.click(valenceLegend)

    expect(valenceLegend).toHaveAttribute('aria-pressed', 'true')
    expect(container.querySelectorAll('.recharts-line-curve')).toHaveLength(2)
  })
})
