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

  it('merges intensity points with emotion timeline and returns emotion heatmap', async () => {
    const range = {
      from: '2026-01-01T12:00:00Z',
      to: '2026-01-01T12:10:00Z',
    }

    vi.mocked(api.fetchIntensity).mockResolvedValue([
      { ts: '2026-01-01T12:01:00Z', value: 0.7 },
    ])
    vi.mocked(api.fetchUsage).mockResolvedValue([])
    vi.mocked(api.fetchTimeline).mockResolvedValue([])
    vi.mocked(api.fetchValence).mockResolvedValue([])
    vi.mocked(api.fetchArousal).mockResolvedValue([])
    vi.mocked(api.fetchStringTimeline).mockResolvedValue([
      { ts: '2026-01-01T12:01:00Z', value: 'curious' },
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
