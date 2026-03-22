import { act, renderHook, waitFor } from '@testing-library/react'

import * as api from '@/api'
import { useHistoryData } from '@/hooks/use-history-data'

vi.mock('@/api', () => ({
  fetchArousal: vi.fn(),
  fetchCurrent: vi.fn(),
  fetchIntensity: vi.fn(),
  fetchLogs: vi.fn(),
  fetchMemoryNetwork: vi.fn(),
  fetchMetric: vi.fn(),
  fetchNotions: vi.fn(),
  fetchStringHeatmap: vi.fn(),
  fetchStringTimeline: vi.fn(),
  fetchTimeline: vi.fn(),
  fetchUsage: vi.fn(),
  fetchValence: vi.fn(),
}))

describe('useHistoryData', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('builds emotion trend, markers, and dynamic desire series from history data', async () => {
    const range = {
      from: '2026-01-01T12:00:00Z',
      to: '2026-01-01T12:10:00Z',
    }

    vi.mocked(api.fetchCurrent).mockResolvedValue({
      tool_calls_per_min: 1,
      error_rate: 0,
      window_24h: { tool_calls: 1, error_rate: 0 },
      latest_desires: { curiosity: 0.9, social_thirst: 0.4, novelty: 0.8 },
      latest_emergent_desires: { momentum: 0.6 },
      latest: {
        ts: '2026-01-01T12:05:00Z',
        emotion_primary: 'curious',
        emotion_intensity: 0.7,
        string_metrics: {
          impulse_boosted_desire: 'curiosity',
        },
        numeric_metrics: {
          impulse_boost_amount: 0.2,
        },
      },
    })
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
    vi.mocked(api.fetchLogs).mockResolvedValue([
      {
        ts: '2026-01-01T12:01:00Z',
        level: 'INFO',
        logger: 'ego_mcp.server',
        message: 'Proust event',
        private: false,
        fields: {
          proust_triggered: true,
          proust_memory_id: 'mem-1',
          proust_memory_decay: 0.88,
          impulse_boost_triggered: true,
          impulse_boosted_desire: 'curiosity',
          impulse_boost_amount: 0.2,
          emergent_desire_created: 'novelty',
        },
      },
    ])
    vi.mocked(api.fetchMemoryNetwork).mockResolvedValue({
      nodes: [{ id: 'mem-1', category: 'memory', is_notion: false }],
      edges: [],
    })
    vi.mocked(api.fetchNotions).mockResolvedValue({
      items: [
        {
          id: 'notion-1',
          label: 'Pattern seeking',
          emotion_tone: 'curious',
          confidence: 0.82,
          source_count: 3,
          source_memory_ids: ['mem-1'],
          created: '2026-01-01T11:00:00Z',
          last_reinforced: '2026-01-01T12:00:00Z',
        },
      ],
    })
    vi.mocked(api.fetchMetric).mockImplementation(async (key: string) => [
      {
        ts: '2026-01-01T12:00:00Z',
        value: key === 'novelty' ? 0.8 : key === 'momentum' ? 0.6 : 0.1,
      },
    ])

    const { result } = renderHook(() => useHistoryData('history', range, '15m'))

    await waitFor(() => {
      expect(result.current.intensity).toHaveLength(1)
      expect(result.current.historyMarkers.length).toBeGreaterThan(0)
    })

    expect(
      (result.current.intensity[0] as { emotion_primary?: string })
        .emotion_primary,
    ).toBe('curious')
    expect(result.current.emotionHeatmap).toEqual([
      { ts: '2026-01-01T12:00:00Z', counts: { curious: 2 } },
    ])
    expect(result.current.emotionTrend).toEqual([
      { ts: '2026-01-01T12:00:30Z', value: 0, emotion_primary: 'neutral' },
      { ts: '2026-01-01T12:01:00Z', value: 0.4, emotion_primary: 'curious' },
      { ts: '2026-01-01T12:02:00Z', value: -0.6, emotion_primary: 'sad' },
    ])
    expect(
      result.current.historyMarkers.map((marker) => marker.kind).sort(),
    ).toEqual(['emergent', 'impulse', 'proust'])
    expect(result.current.memoryNetwork.nodes).toHaveLength(1)
    expect(result.current.notions).toHaveLength(1)
    expect(result.current.desireKeys).toContain('novelty')
    expect(result.current.desireKeys).toContain('momentum')
    expect(result.current.desireChartData).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ novelty: 0.8 }),
        expect.objectContaining({ momentum: 0.6 }),
      ]),
    )
    expect(api.fetchStringTimeline).toHaveBeenCalledWith(
      'emotion_primary',
      range,
    )
    expect(api.fetchStringHeatmap).toHaveBeenCalledWith(
      'emotion_primary',
      range,
      '1m',
    )
    expect(api.fetchMetric).toHaveBeenCalledWith('novelty', range, '1m')
    expect(api.fetchMetric).toHaveBeenCalledWith('momentum', range, '1m')
  })

  it('keeps memory network and notions on a slower refresh cadence', async () => {
    vi.useFakeTimers()
    const range = {
      from: '2026-01-01T12:00:00Z',
      to: '2026-01-01T12:10:00Z',
    }

    vi.mocked(api.fetchCurrent).mockResolvedValue({
      tool_calls_per_min: 1,
      error_rate: 0,
      window_24h: { tool_calls: 1, error_rate: 0 },
      latest_desires: {},
      latest_emergent_desires: {},
      latest: { ts: '2026-01-01T12:05:00Z' },
    })
    vi.mocked(api.fetchIntensity).mockResolvedValue([])
    vi.mocked(api.fetchUsage).mockResolvedValue([])
    vi.mocked(api.fetchTimeline).mockResolvedValue([])
    vi.mocked(api.fetchValence).mockResolvedValue([])
    vi.mocked(api.fetchArousal).mockResolvedValue([])
    vi.mocked(api.fetchStringTimeline).mockResolvedValue([])
    vi.mocked(api.fetchStringHeatmap).mockResolvedValue([])
    vi.mocked(api.fetchLogs).mockResolvedValue([])
    vi.mocked(api.fetchMemoryNetwork).mockResolvedValue({
      nodes: [],
      edges: [],
    })
    vi.mocked(api.fetchNotions).mockResolvedValue({ items: [] })
    vi.mocked(api.fetchMetric).mockResolvedValue([])

    const { result } = renderHook(() => useHistoryData('history', range, '15m'))

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    expect(api.fetchMemoryNetwork).toHaveBeenCalledTimes(1)
    expect(api.fetchNotions).toHaveBeenCalledTimes(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })

    expect(api.fetchCurrent).toHaveBeenCalledTimes(2)
    expect(api.fetchMemoryNetwork).toHaveBeenCalledTimes(1)
    expect(api.fetchNotions).toHaveBeenCalledTimes(1)
    expect(result.current.memoryNetwork).toEqual({ nodes: [], edges: [] })
    expect(result.current.notions).toEqual([])
  })
})
