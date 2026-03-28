import {
  fetchDesireKeys,
  fetchLogs,
  fetchMemoryNetwork,
  fetchNotionHistory,
  fetchNotions,
  fetchStringHeatmap,
  fetchStringTimeline,
} from '@/api'

describe('api.fetchLogs', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T12:10:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('fetches recent logs when called without explicit range', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [
          {
            ts: '2026-01-01T12:09:00Z',
            level: 'INFO',
            logger: 'ego_mcp.server',
            message: 'Tool invocation',
            private: false,
            fields: { tool_name: 'remember' },
          },
        ],
      }),
    } as Response)

    const logs = await fetchLogs()
    const url = String(vi.mocked(globalThis.fetch).mock.calls[0]?.[0] ?? '')

    expect(url).toContain('/api/v1/logs?from=')
    expect(url).toContain('&to=')
    expect(logs[0]?.tool_name).toBe('remember')
    expect(logs[0]?.ok).toBe(true)
  })

  it('uses search query parameter for filtered log fetch', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ items: [] }),
    } as Response)

    await fetchLogs(
      { from: '2026-01-01T12:00:00Z', to: '2026-01-01T12:10:00Z' },
      'INFO',
      'remember',
    )
    const url = String(vi.mocked(globalThis.fetch).mock.calls[0]?.[0] ?? '')

    expect(url).toContain('level=INFO')
    expect(url).toContain('search=remember')
    expect(url).not.toContain('logger=')
  })
})

describe('api string metric fetchers', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('fetches string timeline for an arbitrary key', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ items: [] }),
    } as Response)

    await fetchStringTimeline('emotion_primary', {
      from: '2026-01-01T12:00:00Z',
      to: '2026-01-01T12:10:00Z',
    })
    const url = String(vi.mocked(globalThis.fetch).mock.calls[0]?.[0] ?? '')

    expect(url).toContain('/api/v1/metrics/emotion_primary/string-timeline?')
  })

  it('fetches string heatmap for an arbitrary key', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ items: [] }),
    } as Response)

    await fetchStringHeatmap(
      'emotion_primary',
      {
        from: '2026-01-01T12:00:00Z',
        to: '2026-01-01T12:10:00Z',
      },
      '5m',
    )
    const url = String(vi.mocked(globalThis.fetch).mock.calls[0]?.[0] ?? '')

    expect(url).toContain('/api/v1/metrics/emotion_primary/heatmap?')
    expect(url).toContain('bucket=5m')
  })
})

describe('api history extensions', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('fetches the memory network panel payload', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ nodes: [], edges: [] }),
    } as Response)

    await fetchMemoryNetwork()
    const url = String(vi.mocked(globalThis.fetch).mock.calls[0]?.[0] ?? '')

    expect(url).toContain('/api/v1/memory/network')
  })

  it('fetches notions and notion history', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ items: [] }),
    } as Response)

    await fetchNotions()
    const notionsUrl = String(
      vi.mocked(globalThis.fetch).mock.calls[0]?.[0] ?? '',
    )
    await fetchNotionHistory(
      'notion-1',
      {
        from: '2026-01-01T12:00:00Z',
        to: '2026-01-01T12:10:00Z',
      },
      '15m',
    )

    const notionHistoryUrl = String(
      vi.mocked(globalThis.fetch).mock.calls[1]?.[0] ?? '',
    )

    expect(notionsUrl).toContain('/api/v1/notions')
    expect(notionHistoryUrl).toContain('/api/v1/notions/notion-1/history?')
    expect(notionHistoryUrl).toContain('bucket=15m')
  })

  it('fetches desire metric keys in a range', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ items: [] }),
    } as Response)

    await fetchDesireKeys({
      from: '2026-01-01T12:00:00Z',
      to: '2026-01-01T12:10:00Z',
    })
    const url = String(vi.mocked(globalThis.fetch).mock.calls[0]?.[0] ?? '')

    expect(url).toContain('/api/v1/desires/keys?')
  })
})
