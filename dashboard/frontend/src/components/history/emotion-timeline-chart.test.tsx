import { render, screen } from '@testing-library/react'

import { EmotionTimelineChart } from '@/components/history/emotion-timeline-chart'
import type { EmotionTrendPoint, HistoryMarker } from '@/types'

describe('EmotionTimelineChart', () => {
  it('renders card title', () => {
    render(<EmotionTimelineChart points={[]} />)

    expect(screen.getByText('Emotion trend')).toBeInTheDocument()
  })

  it('accepts timeline points with positive and negative values', () => {
    const points: EmotionTrendPoint[] = [
      { ts: '2026-01-01T12:01:00Z', value: 0.4, emotion_primary: 'curious' },
      { ts: '2026-01-01T12:02:00Z', value: -0.6, emotion_primary: 'sad' },
    ]
    const markers: HistoryMarker[] = [
      {
        ts: '2026-01-01T12:01:00Z',
        kind: 'proust',
        label: 'Proust',
        detail: 'mem-1',
      },
    ]

    render(<EmotionTimelineChart points={points} markers={markers} />)

    expect(screen.getByText('Emotion trend')).toBeInTheDocument()
    expect(screen.getByText('Proust mem-1')).toBeInTheDocument()
  })
})
