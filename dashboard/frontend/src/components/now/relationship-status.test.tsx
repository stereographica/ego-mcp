import { render, screen } from '@testing-library/react'

import { RelationshipStatus } from '@/components/now/relationship-status'
import type { CurrentResponse } from '@/types'

describe('RelationshipStatus', () => {
  it('renders latest relationship values', () => {
    const current: CurrentResponse = {
      tool_calls_per_min: 1,
      error_rate: 0,
      latest: null,
      latest_relationship: {
        trust_level: 0.82,
        total_interactions: 15,
        shared_episodes_count: 3,
      },
    }

    render(<RelationshipStatus current={current} />)

    expect(screen.getByText('0.82')).toBeInTheDocument()
    expect(screen.getByText('15')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('renders default values when current is null', () => {
    render(<RelationshipStatus current={null} />)

    expect(screen.getByText('0.00')).toBeInTheDocument()
    expect(screen.getAllByText('0')).toHaveLength(2)
  })
})
