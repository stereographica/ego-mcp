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
})
