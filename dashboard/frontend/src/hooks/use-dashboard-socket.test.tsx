import { render, screen, waitFor } from '@testing-library/react'

import { fetchCurrent, fetchLogs } from '@/api'
import { useDashboardSocket } from '@/hooks/use-dashboard-socket'

vi.mock('@/api', () => ({
  fetchCurrent: vi.fn(async () => ({
    tool_calls_per_min: 1,
    error_rate: 0,
    latest: { ts: '2026-01-01T12:00:00Z' },
    latest_emotion: null,
  })),
  fetchLogs: vi.fn(async () => [
    {
      ts: '2026-01-01T12:00:00Z',
      tool_name: 'remember',
      ok: true,
      level: 'INFO',
      logger: 'ego_mcp.server',
      message: 'Tool invocation',
      private: false,
    },
  ]),
}))

const Probe = () => {
  const { connected, logLines } = useDashboardSocket()
  return (
    <div>
      <span data-testid="connected">{String(connected)}</span>
      <span data-testid="count">{logLines.length}</span>
      <span data-testid="tool">{logLines[0]?.tool_name ?? ''}</span>
    </div>
  )
}

describe('useDashboardSocket', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'WebSocket',
      class {
        constructor() {
          throw new Error('ws unavailable')
        }
      },
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('updates log lines while falling back to HTTP polling', async () => {
    render(<Probe />)

    await waitFor(() => {
      expect(fetchCurrent).toHaveBeenCalled()
      expect(fetchLogs).toHaveBeenCalled()
      expect(screen.getByTestId('count')).toHaveTextContent('1')
    })
    expect(screen.getByTestId('tool')).toHaveTextContent('remember')
    expect(screen.getByTestId('connected')).toHaveTextContent('false')
  })

  it('keeps log lines when only level differs', async () => {
    vi.mocked(fetchLogs).mockResolvedValueOnce([
      {
        ts: '2026-01-01T12:00:00Z',
        tool_name: 'remember',
        ok: true,
        level: 'INFO',
        logger: 'ego_mcp.server',
        message: 'Tool invocation',
        private: false,
      },
      {
        ts: '2026-01-01T12:00:00Z',
        tool_name: 'remember',
        ok: false,
        level: 'ERROR',
        logger: 'ego_mcp.server',
        message: 'Tool invocation',
        private: false,
      },
    ])

    render(<Probe />)

    await waitFor(() => {
      expect(fetchLogs).toHaveBeenCalled()
      expect(screen.getByTestId('count')).toHaveTextContent('2')
    })
  })
})
