import { StrictMode } from 'react'
import { act, render, screen, waitFor } from '@testing-library/react'

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

class MockWebSocket {
  static instances: MockWebSocket[] = []

  onopen: (() => void) | null = null
  onmessage: ((evt: MessageEvent) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null

  constructor(url: string) {
    void url
    MockWebSocket.instances.push(this)
  }

  static reset(): void {
    MockWebSocket.instances = []
  }

  emitOpen(): void {
    this.onopen?.()
  }

  emitMessage(payload: unknown): void {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent)
  }

  close(): void {
    setTimeout(() => {
      this.onclose?.()
    }, 0)
  }
}

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
    MockWebSocket.reset()
    vi.clearAllMocks()
    vi.useRealTimers()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('updates log lines while falling back to HTTP polling', async () => {
    vi.stubGlobal(
      'WebSocket',
      class {
        constructor() {
          throw new Error('ws unavailable')
        }
      },
    )

    render(<Probe />)

    await waitFor(() => {
      expect(fetchCurrent).toHaveBeenCalled()
      expect(fetchLogs).toHaveBeenCalled()
      expect(screen.getByTestId('count')).toHaveTextContent('1')
    })
    expect(screen.getByTestId('tool')).toHaveTextContent('remember')
    expect(screen.getByTestId('connected')).toHaveTextContent('false')
  })

  it('keeps websocket connection during StrictMode remount and ignores stale close', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)

    render(
      <StrictMode>
        <Probe />
      </StrictMode>,
    )

    expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(2)

    const latest = MockWebSocket.instances[MockWebSocket.instances.length - 1]
    expect(latest).toBeDefined()

    act(() => {
      latest.emitOpen()
    })
    expect(screen.getByTestId('connected')).toHaveTextContent('true')

    await act(async () => {
      vi.runOnlyPendingTimers()
    })

    expect(screen.getByTestId('connected')).toHaveTextContent('true')
    expect(fetchLogs).not.toHaveBeenCalled()
  })

  it('falls back to polling and reconnects after websocket close', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)

    render(<Probe />)

    expect(MockWebSocket.instances.length).toBe(1)
    const socket = MockWebSocket.instances[0]

    act(() => {
      socket.emitOpen()
    })
    expect(screen.getByTestId('connected')).toHaveTextContent('true')

    await act(async () => {
      socket.close()
      vi.runOnlyPendingTimers()
    })

    expect(fetchLogs).toHaveBeenCalled()
    expect(screen.getByTestId('connected')).toHaveTextContent('false')

    const beforeReconnect = MockWebSocket.instances.length
    await act(async () => {
      vi.advanceTimersByTime(3_000)
    })

    expect(MockWebSocket.instances.length).toBeGreaterThan(beforeReconnect)
  })

  it('keeps distinct log lines when level differs', async () => {
    vi.stubGlobal(
      'WebSocket',
      class {
        constructor() {
          throw new Error('ws unavailable')
        }
      },
    )
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
