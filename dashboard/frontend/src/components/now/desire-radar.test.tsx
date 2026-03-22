import { render, screen } from '@testing-library/react'

import { DesireRadar } from '@/components/now/desire-radar'

describe('DesireRadar', () => {
  it('shows dynamic axes and impulse boost badge', () => {
    render(
      <DesireRadar
        current={{
          tool_calls_per_min: 3,
          error_rate: 0.1,
          window_24h: { tool_calls: 20, error_rate: 0.05 },
          latest_desires: { curiosity: 0.8 },
          latest_emergent_desires: { novelty: 0.6 },
          latest: {
            emotion_primary: 'curious',
            emotion_intensity: 0.7,
            string_metrics: { impulse_boosted_desire: 'curiosity' },
            numeric_metrics: { impulse_boost_amount: 0.2 },
          },
        }}
      />,
    )

    expect(screen.getByText('Desire parameters')).toBeInTheDocument()
    expect(screen.getByText('dynamic axes')).toBeInTheDocument()
    expect(screen.getByText(/impulse boost curiosity/)).toBeInTheDocument()
  })
})
