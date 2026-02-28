import { render, screen, waitFor } from '@testing-library/react'

import { fetchUsage } from '@/api'
import { SessionSummary } from '@/components/now/session-summary'

vi.mock('@/api', () => ({
  fetchUsage: vi.fn(),
}))

vi.mock('@/hooks/use-timestamp-formatter', () => ({
  useTimestampFormatter: () => ({ clientTimeZone: 'UTC' }),
}))

describe('SessionSummary', () => {
  it('shows today/yesterday tool calls and hides latest latency', async () => {
    vi.mocked(fetchUsage)
      .mockResolvedValueOnce([{ ts: '2026-01-01T00:00:00Z', remember: 2 }])
      .mockResolvedValueOnce([{ ts: '2025-12-31T00:00:00Z', recall: 1 }])

    render(<SessionSummary />)

    expect(screen.getByText('tool calls (today)')).toBeInTheDocument()
    expect(screen.getByText('tool calls (yesterday)')).toBeInTheDocument()
    expect(screen.queryByText('latest latency')).not.toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('2')).toBeInTheDocument()
      expect(screen.getByText('1')).toBeInTheDocument()
    })
  })
})
