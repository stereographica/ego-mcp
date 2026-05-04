import { render, screen } from '@testing-library/react'

import { SurfaceTimeline } from '@/components/relationships/surface-timeline'
import { buildSurfaceTimelineData } from '@/components/relationships/surface-timeline-utils'
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
  it('maps person names and sorts timeline data by timestamp', () => {
    const personNameMap = new Map(
      mockPersons.map((person) => [person.person_id, person.name]),
    )

    expect(buildSurfaceTimelineData(mockPoints, personNameMap)).toEqual([
      {
        ts: new Date('2026-01-01T12:00:00+00:00').getTime(),
        tsLabel: '2026-01-01T12:00:00+00:00',
        person_id: 'alice',
        display_name: 'Alice',
        surface_type: 'resonant',
        fill: '#3b82f6',
      },
      {
        ts: new Date('2026-01-01T14:00:00+00:00').getTime(),
        tsLabel: '2026-01-01T14:00:00+00:00',
        person_id: 'bob',
        display_name: 'Bob',
        surface_type: 'involuntary',
        fill: '#f59e0b',
      },
    ])
  })

  it('renders empty state when no points', () => {
    render(
      <SurfaceTimeline points={[]} isLoading={false} persons={mockPersons} />,
    )

    expect(screen.getByText('Surface timeline')).toBeInTheDocument()
    expect(screen.getByText(/No surface events recorded/i)).toBeInTheDocument()
  })

  it('renders loading state when isLoading', () => {
    render(
      <SurfaceTimeline points={[]} isLoading={true} persons={mockPersons} />,
    )

    expect(screen.getByText('Surface timeline')).toBeInTheDocument()
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
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getAllByText('Bob').length).toBeGreaterThan(0)

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
