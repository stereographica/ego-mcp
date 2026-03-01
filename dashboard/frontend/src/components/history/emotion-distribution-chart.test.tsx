import { render, screen } from '@testing-library/react'

import { EmotionDistributionChart } from '@/components/history/emotion-distribution-chart'
import { aggregateEmotionCounts } from '@/components/history/emotion-distribution-utils'
import type { HeatmapPoint } from '@/types'

describe('EmotionDistributionChart', () => {
  it('renders card title', () => {
    render(<EmotionDistributionChart heatmapData={[]} />)

    expect(screen.getByText('Emotion distribution')).toBeInTheDocument()
  })

  it('aggregates counts from multiple buckets', () => {
    const heatmapData: HeatmapPoint[] = [
      { ts: '2026-01-01T12:00:00Z', counts: { curious: 2, calm: 1 } },
      { ts: '2026-01-01T12:05:00Z', counts: { curious: 3, alert: 4 } },
    ]

    const aggregated = aggregateEmotionCounts(heatmapData)

    expect(aggregated).toEqual([
      { emotion: 'curious', count: 5 },
      { emotion: 'alert', count: 4 },
      { emotion: 'calm', count: 1 },
    ])
  })
})
