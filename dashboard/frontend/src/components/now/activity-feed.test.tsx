import { render, screen } from '@testing-library/react'

import { ActivityFeed } from '@/components/now/activity-feed'

describe('ActivityFeed', () => {
  it('shows HTTP polling indicator when websocket is disconnected', () => {
    render(<ActivityFeed logLines={[]} connected={false} />)

    expect(screen.getByText('HTTP polling')).toBeInTheDocument()
    expect(screen.getByText('Waiting for activity...')).toBeInTheDocument()
  })

  it('shows WebSocket indicator when connected', () => {
    render(<ActivityFeed logLines={[]} connected={true} />)

    expect(screen.getByText('WebSocket')).toBeInTheDocument()
  })

  it('truncates long tool names to avoid horizontal overflow', () => {
    render(
      <ActivityFeed
        connected={true}
        logLines={[
          {
            ts: '2025-01-01T00:00:00.000Z',
            ok: true,
            tool_name: 'this-is-an-extremely-long-tool-name-for-mobile-layouts',
            message: 'example',
          },
        ]}
      />,
    )

    const toolBadge = screen.getByText(
      'this-is-an-extremely-long-tool-name-for-mobile-layouts',
    )
    expect(toolBadge).toHaveClass('max-w-[8rem]', 'truncate')
  })

  it('applies overflow clipping to the card container', () => {
    const { container } = render(
      <ActivityFeed logLines={[]} connected={true} />,
    )

    expect(container.firstChild).toHaveClass('overflow-hidden')
  })

  it('does not call scrollIntoView when appending log lines', () => {
    const scrollIntoView = vi.fn()
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: scrollIntoView,
    })

    render(
      <ActivityFeed
        connected={true}
        logLines={[
          {
            ts: '2025-01-01T00:00:00.000Z',
            ok: true,
            message: 'hello',
          },
        ]}
      />,
    )

    expect(scrollIntoView).not.toHaveBeenCalled()
  })
})
