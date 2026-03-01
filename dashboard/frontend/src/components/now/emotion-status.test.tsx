import { render, screen } from '@testing-library/react'

import { EmotionStatus } from '@/components/now/emotion-status'
import type { CurrentResponse } from '@/types'

describe('EmotionStatus', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T12:10:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('prefers latest_emotion and shows its timestamp', () => {
    const current: CurrentResponse = {
      tool_calls_per_min: 1,
      error_rate: 0,
      latest: {
        ts: '2026-01-01T12:10:00Z',
        emotion_primary: 'neutral',
        emotion_intensity: 0.1,
        numeric_metrics: { valence: 0.1, arousal: 0.2 },
      },
      latest_emotion: {
        ts: '2026-01-01T12:05:00Z',
        emotion_primary: 'curious',
        emotion_intensity: 0.7,
        valence: 0.4,
        arousal: 0.8,
      },
    }

    render(<EmotionStatus current={current} />)

    expect(screen.getByText('curious')).toBeInTheDocument()
    expect(screen.getByText('0.70')).toBeInTheDocument()
    expect(screen.getByTestId('circumplex-chart')).toBeInTheDocument()
    expect(screen.getByText(/v: 0.40/i)).toBeInTheDocument()
    expect(screen.getByText(/a: 0.80/i)).toBeInTheDocument()
    expect(screen.getByText(/5m ago/)).toBeInTheDocument()
  })

  it('falls back to latest when latest_emotion is not available', () => {
    const current: CurrentResponse = {
      tool_calls_per_min: 1,
      error_rate: 0,
      latest: {
        ts: '2026-01-01T12:09:00Z',
        emotion_primary: 'calm',
        emotion_intensity: 0.6,
        numeric_metrics: { valence: 0.2, arousal: 0.3 },
      },
      latest_emotion: null,
    }

    render(<EmotionStatus current={current} />)

    expect(screen.getByText('calm', { selector: 'span' })).toBeInTheDocument()
    expect(screen.getByText('0.60')).toBeInTheDocument()
    expect(screen.getByText(/v: 0.20/i)).toBeInTheDocument()
    expect(screen.getByText(/a: 0.30/i)).toBeInTheDocument()
  })
})
