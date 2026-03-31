import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import App from './App'

vi.mock('./api', () => ({
  fetchDesireCatalog: async () => ({
    items: [
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
      {
        id: 'curiosity',
        display_name: 'curiosity',
        maslow_level: 2,
      },
    ],
  }),
  fetchDesireKeys: async () => ['novelty', 'cognitive_coherence'],
  fetchCurrent: async () => ({
    tool_calls_per_min: 4,
    error_rate: 0.25,
    window_24h: { tool_calls: 3, error_rate: 0.125 },
    latest_desires: { curiosity: 0.9, social_thirst: 0.4 },
    latest: {
      ts: new Date().toISOString(),
      emotion_primary: 'curious',
      emotion_intensity: 0.7,
      duration_ms: 120,
      numeric_metrics: { valence: 0.5, arousal: 0.6 },
    },
  }),
  fetchIntensity: async () => [{ ts: '2026-01-01T12:00:00Z', value: 0.7 }],
  fetchMetric: async () => [{ ts: '2026-01-01T12:00:00Z', value: 0.5 }],
  fetchMemoryNetwork: async () => ({ nodes: [], edges: [] }),
  fetchNotions: async () => ({ items: [] }),
  fetchUsage: async () => [
    { ts: '2026-01-01T12:00:00Z', feel_desires: 2, remember: 1 },
  ],
  fetchTimeline: async () => [{ ts: '2026-01-01T12:00:00Z', value: 'night' }],
  fetchHeatmap: async () => [],
  fetchStringHeatmap: async () => [],
  fetchStringTimeline: async () => [],
  fetchLogs: async () => [
    {
      ts: '2026-01-01T12:00:00Z',
      level: 'INFO',
      logger: 'test',
      message: 'ok',
      private: false,
    },
  ],
  fetchAnomalies: async () => [],
  fetchValence: async () => [{ ts: '2026-01-01T12:00:00Z', value: 0.5 }],
  fetchArousal: async () => [{ ts: '2026-01-01T12:00:00Z', value: 0.6 }],
}))

describe('App', () => {
  it('shows now tab summary cards with local-day tool calls', async () => {
    render(<App />)
    expect(await screen.findByText('tool calls (today)')).toBeInTheDocument()
    expect(
      await screen.findByText('tool calls (yesterday)'),
    ).toBeInTheDocument()
    expect(await screen.findByText('curious')).toBeInTheDocument()
  })

  it('shows status indicator', async () => {
    render(<App />)
    expect(await screen.findByText('Active')).toBeInTheDocument()
  })

  it('shows desire radar chart section', async () => {
    render(<App />)
    expect(await screen.findByText('Desire parameters')).toBeInTheDocument()
  })

  it('shows logs tab with live tail heading and default search filter', async () => {
    render(<App />)
    await userEvent.click(screen.getByRole('tab', { name: 'Logs' }))
    expect(await screen.findByText('Live tail')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('search logs...')).toHaveValue('')
  })

  it('shows history controls and the desire history chart when history is selected', async () => {
    const user = userEvent.setup()
    const { container } = render(<App />)

    await user.click(screen.getByRole('tab', { name: 'History' }))

    expect(
      await screen.findByText('Desire parameter history'),
    ).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'custom' })).toBeInTheDocument()

    await user.click(screen.getByRole('radio', { name: 'custom' }))

    expect(
      container.querySelectorAll('input[type="datetime-local"]'),
    ).toHaveLength(2)
  })
})
