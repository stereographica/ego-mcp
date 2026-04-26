import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DashboardHeader } from './dashboard-header'

describe('DashboardHeader', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('shows the agent name when VITE_DASHBOARD_AGENT_NAME is set', () => {
    vi.stubEnv('VITE_DASHBOARD_AGENT_NAME', 'orchid-7')

    render(<DashboardHeader current={null} connected={true} />)

    expect(screen.getByLabelText('agent name')).toHaveTextContent('orchid-7')
  })

  it('omits the agent name when the env var is unset or blank', () => {
    vi.stubEnv('VITE_DASHBOARD_AGENT_NAME', '   ')

    render(<DashboardHeader current={null} connected={true} />)

    expect(screen.queryByLabelText('agent name')).not.toBeInTheDocument()
  })
})
