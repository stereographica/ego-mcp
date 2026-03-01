import { render, screen } from '@testing-library/react'

import { CircumplexCard } from '@/components/now/circumplex-card'
import type { CurrentResponse } from '@/types'

describe('CircumplexCard', () => {
  it('uses latest_emotion valence/arousal when available', () => {
    const current: CurrentResponse = {
      tool_calls_per_min: 1,
      error_rate: 0,
      latest: {
        numeric_metrics: { valence: 0.1, arousal: 0.2 },
      },
      latest_emotion: {
        ts: '2026-01-01T12:00:00Z',
        emotion_primary: 'curious',
        emotion_intensity: 0.7,
        valence: 0.4,
        arousal: 0.8,
      },
    }

    render(<CircumplexCard current={current} />)

    expect(screen.getByText('Valence-Arousal')).toBeInTheDocument()
    expect(screen.getByTestId('circumplex-dot')).toBeInTheDocument()
    expect(screen.getByText(/v: 0.40/i)).toBeInTheDocument()
    expect(screen.getByText(/a: 0.80/i)).toBeInTheDocument()
  })

  it('shows n/a when current is null', () => {
    render(<CircumplexCard current={null} />)

    expect(screen.getByTestId('circumplex-na')).toBeInTheDocument()
  })
})
