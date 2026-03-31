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
          latest_desires: { information_hunger: 0.7, old_fixed: 0.9 },
          latest_emergent_desires: { novelty: 0.6 },
          latest: {
            emotion_primary: 'curious',
            emotion_intensity: 0.7,
            string_metrics: { impulse_boosted_desire: 'curiosity' },
            numeric_metrics: { impulse_boost_amount: 0.2 },
          },
        }}
        desireCatalog={[
          {
            id: 'information_hunger',
            display_name: 'information hunger',
            maslow_level: 1,
          },
          {
            id: 'social_thirst',
            display_name: 'social thirst',
            maslow_level: 1,
          },
        ]}
      />,
    )

    expect(screen.getByText('Desire parameters')).toBeInTheDocument()
    expect(screen.getByText('dynamic axes')).toBeInTheDocument()
    expect(screen.getByText(/impulse boost curiosity/)).toBeInTheDocument()
  })

  it('hides auxiliary badges when there are no dynamic desires or impulse boosts', () => {
    render(
      <DesireRadar
        current={{
          tool_calls_per_min: 3,
          error_rate: 0.1,
          window_24h: { tool_calls: 20, error_rate: 0.05 },
          latest_desires: { information_hunger: 0.7 },
          latest_emergent_desires: {},
          latest: {
            emotion_primary: 'curious',
            emotion_intensity: 0.7,
            string_metrics: {},
            numeric_metrics: {},
          },
        }}
        desireCatalog={[
          {
            id: 'information_hunger',
            display_name: 'information hunger',
            maslow_level: 1,
          },
        ]}
      />,
    )

    expect(screen.getByText('Desire parameters')).toBeInTheDocument()
    expect(screen.queryByText('dynamic axes')).not.toBeInTheDocument()
    expect(screen.queryByText(/impulse boost/)).not.toBeInTheDocument()
  })
})
