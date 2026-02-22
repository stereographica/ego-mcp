import { render, screen } from '@testing-library/react'

import App from './App'

vi.mock('./api', () => ({
  fetchCurrent: async () => ({
    tool_calls_per_min: 4,
    error_rate: 0.25,
    latest: { emotion_primary: 'curious', emotion_intensity: 0.7 },
  }),
  fetchIntensity: async () => [{ ts: '2026-01-01T12:00:00Z', value: 0.7 }],
  fetchUsage: async () => [
    { ts: '2026-01-01T12:00:00Z', feel_desires: 2, remember: 1 },
  ],
  fetchTimeline: async () => [{ ts: '2026-01-01T12:00:00Z', value: 'night' }],
  fetchHeatmap: async () => [
    { ts: '2026-01-01T12:00:00Z', counts: { night: 1 } },
  ],
  fetchLogs: async () => [
    {
      ts: '2026-01-01T12:00:00Z',
      level: 'INFO',
      logger: 'test',
      message: 'ok',
      private: false,
    },
  ],
}))

describe('App', () => {
  it('shows now tab summary cards with range total tool calls', async () => {
    render(<App />)
    expect(await screen.findByText('tool calls (1h total)')).toBeInTheDocument()
    expect(await screen.findByText('3')).toBeInTheDocument()
    expect(await screen.findByText('curious')).toBeInTheDocument()
  })
})
