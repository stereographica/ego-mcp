import { render, screen } from '@testing-library/react'

import { SurfaceTimeline } from '@/components/relationships/surface-timeline'
import type { PersonOverview, SurfaceTimelinePoint } from '@/types'

const mockPoints: SurfaceTimelinePoint[] = [
  {
    ts: '2026-01-01T12:00:00+00:00',
    person_id: 'alice',
    surface_type: 'resonant',
  },
  {
    ts: '2026-01-01T14:00:00+00:00',
    person_id: 'bob',
    surface_type: 'involuntary',
  },
]

const mockPersons: PersonOverview[] = [
  {
    person_id: 'alice',
    name: 'Alice',
    relation_kind: 'interlocutor',
    trust_level: 0.8,
    total_interactions: 10,
    shared_episodes_count: 3,
    last_interaction: '2026-01-01T12:00:00+00:00',
    first_interaction: '2026-01-01T10:00:00+00:00',
    aliases: [],
  },
  {
    person_id: 'bob',
    name: 'Bob',
    relation_kind: 'mentioned',
    trust_level: null,
    total_interactions: 0,
    shared_episodes_count: 0,
    last_interaction: '',
    first_interaction: '',
    aliases: [],
  },
]

describe('SurfaceTimeline', () => {
  it('renders empty state when no points', () => {
    render(
      <SurfaceTimeline points={[]} isLoading={false} persons={mockPersons} />,
    )

    expect(screen.getByText(/No surface events recorded/i)).toBeInTheDocument()
  })

  it('renders loading state when isLoading', () => {
    render(
      <SurfaceTimeline points={[]} isLoading={true} persons={mockPersons} />,
    )

    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('renders chart with data and chart container', () => {
    render(
      <SurfaceTimeline
        points={mockPoints}
        isLoading={false}
        persons={mockPersons}
      />,
    )

    expect(screen.getByText('Surface timeline')).toBeInTheDocument()

    const chartContainers = document.querySelectorAll('[data-chart]')
    expect(chartContainers).toHaveLength(1)
  })

  it('renders with data points when data exists', () => {
    const { rerender } = render(
      <SurfaceTimeline
        points={mockPoints}
        isLoading={false}
        persons={mockPersons}
      />,
    )

    expect(screen.queryByText(/No surface events/i)).not.toBeInTheDocument()

    rerender(
      <SurfaceTimeline points={[]} isLoading={false} persons={mockPersons} />,
    )

    expect(screen.getByText(/No surface events recorded/i)).toBeInTheDocument()
  })
})
