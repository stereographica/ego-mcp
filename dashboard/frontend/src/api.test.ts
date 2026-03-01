import { fetchLogs } from '@/api'

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
