import { renderHook, waitFor } from '@testing-library/react'

import * as api from '@/api'
import { useHistoryData } from '@/hooks/use-history-data'

vi.mock('@/api', () => ({
  fetchArousal: vi.fn(),
  fetchIntensity: vi.fn(),
  fetchMetric: vi.fn(),
  fetchStringHeatmap: vi.fn(),
  fetchStringTimeline: vi.fn(),
  fetchTimeline: vi.fn(),
  fetchUsage: vi.fn(),
  fetchValence: vi.fn(),
}))

describe('useHistoryData', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('builds emotion trend with neutral-centered valence and merged emotion labels', async () => {
    const range = {
      from: '2026-01-01T12:00:00Z',
      to: '2026-01-01T12:10:00Z',
    }

    vi.mocked(api.fetchIntensity).mockResolvedValue([
      { ts: '2026-01-01T12:01:00Z', value: 0.7 },
    ])
    vi.mocked(api.fetchUsage).mockResolvedValue([])
    vi.mocked(api.fetchTimeline).mockResolvedValue([])
    vi.mocked(api.fetchValence).mockResolvedValue([
      { ts: '2026-01-01T12:01:00Z', value: 0.4 },
      { ts: '2026-01-01T12:02:00Z', value: -0.6 },
      { ts: '2026-01-01T12:03:00Z', value: 1.2 },
    ])
    vi.mocked(api.fetchArousal).mockResolvedValue([])
    vi.mocked(api.fetchStringTimeline).mockResolvedValue([
      { ts: '2026-01-01T12:00:30Z', value: 'neutral' },
      { ts: '2026-01-01T12:01:00Z', value: 'curious' },
      { ts: '2026-01-01T12:02:00Z', value: 'sad' },
    ])
    vi.mocked(api.fetchStringHeatmap).mockResolvedValue([
      { ts: '2026-01-01T12:00:00Z', counts: { curious: 2 } },
    ])
    vi.mocked(api.fetchMetric).mockResolvedValue([])

    const { result } = renderHook(() => useHistoryData('history', range, '15m'))

    await waitFor(() => {
      expect(result.current.intensity).toHaveLength(1)
    })

    expect(
      (result.current.intensity[0] as { emotion_primary?: string })
        .emotion_primary,
    ).toBe('curious')
    expect(result.current.emotionHeatmap).toEqual([
      { ts: '2026-01-01T12:00:00Z', counts: { curious: 2 } },
    ])
    expect(result.current.emotionTrend).toEqual([
      { ts: '2026-01-01T12:01:00Z', value: 0.4, emotion_primary: 'curious' },
      { ts: '2026-01-01T12:02:00Z', value: -0.6, emotion_primary: 'sad' },
      { ts: '2026-01-01T12:03:00Z', value: 1, emotion_primary: 'sad' },
    ])
    expect(api.fetchStringTimeline).toHaveBeenCalledWith(
      'emotion_primary',
      range,
    )
    expect(api.fetchStringHeatmap).toHaveBeenCalledWith(
      'emotion_primary',
      range,
      '1m',
    )
  })
})
