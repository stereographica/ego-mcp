import { render, screen, fireEvent, waitFor } from '@testing-library/react'

import { RelationshipsTab } from '@/components/relationships/relationships-tab'
import {
  fetchRelationshipsOverview,
  fetchSurfaceTimeline,
  fetchPersonDetail,
} from '@/api'

vi.mock('@/api', () => ({
  fetchRelationshipsOverview: vi.fn(),
  fetchSurfaceTimeline: vi.fn(),
  fetchPersonDetail: vi.fn(),
}))

const mockRange = {
  from: '2026-01-01T00:00:00+00:00',
  to: '2026-01-02T00:00:00+00:00',
}

describe('RelationshipsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetches overview and surface timeline on mount', async () => {
    vi.mocked(fetchRelationshipsOverview).mockResolvedValue({
      items: [
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
      ],
    })
    vi.mocked(fetchSurfaceTimeline).mockResolvedValue({ items: [] })

    render(<RelationshipsTab range={mockRange} />)

    await waitFor(() => {
      expect(fetchRelationshipsOverview).toHaveBeenCalledTimes(1)
    })
    await waitFor(() => {
      expect(fetchSurfaceTimeline).toHaveBeenCalledTimes(1)
      expect(fetchSurfaceTimeline).toHaveBeenCalledWith(mockRange)
    })
  })

  it('shows person overview table with data', async () => {
    vi.mocked(fetchRelationshipsOverview).mockResolvedValue({
      items: [
        {
          person_id: 'alice',
          name: 'Alice',
          relation_kind: 'interlocutor',
          trust_level: 0.75,
          total_interactions: 20,
          shared_episodes_count: 5,
          last_interaction: '2026-01-01T12:00:00+00:00',
          first_interaction: '2026-01-01T10:00:00+00:00',
          aliases: ['Alicia'],
        },
      ],
    })
    vi.mocked(fetchSurfaceTimeline).mockResolvedValue({ items: [] })

    render(<RelationshipsTab range={mockRange} />)

    await waitFor(() => {
      expect(screen.getByText('Alice')).toBeInTheDocument()
    })
    expect(screen.getByText('20')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('shows empty state when no persons found', async () => {
    vi.mocked(fetchRelationshipsOverview).mockResolvedValue({ items: [] })
    vi.mocked(fetchSurfaceTimeline).mockResolvedValue({ items: [] })

    render(<RelationshipsTab range={mockRange} />)

    await waitFor(() => {
      expect(screen.getByText(/No relationships found/i)).toBeInTheDocument()
    })
  })

  it('shows loading state for overview', async () => {
    vi.mocked(fetchRelationshipsOverview).mockResolvedValue({ items: [] })
    vi.mocked(fetchSurfaceTimeline).mockImplementation(
      () =>
        new Promise(() => {
          /* delay */
        }),
    )

    render(<RelationshipsTab range={mockRange} />)

    await waitFor(() => {
      expect(screen.getByText('Person overview')).toBeInTheDocument()
    })
    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('shows loading state for surface timeline', async () => {
    vi.mocked(fetchRelationshipsOverview).mockResolvedValue({
      items: [
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
      ],
    })
    vi.mocked(fetchSurfaceTimeline).mockImplementation(
      () =>
        new Promise(() => {
          /* delay */
        }),
    )

    render(<RelationshipsTab range={mockRange} />)

    await waitFor(() => {
      expect(screen.getByText('Bob')).toBeInTheDocument()
    })
    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('re-fetches surface timeline when range changes', async () => {
    vi.mocked(fetchRelationshipsOverview).mockResolvedValue({ items: [] })
    vi.mocked(fetchSurfaceTimeline).mockResolvedValue({ items: [] })

    const { rerender } = render(<RelationshipsTab range={mockRange} />)

    await waitFor(() => {
      expect(fetchSurfaceTimeline).toHaveBeenCalledTimes(1)
    })

    const newRange = {
      from: '2026-01-02T00:00:00+00:00',
      to: '2026-01-03T00:00:00+00:00',
    }
    rerender(<RelationshipsTab range={newRange} />)

    await waitFor(() => {
      expect(fetchSurfaceTimeline).toHaveBeenCalledTimes(2)
    })
  })

  it('selects a person and shows detail panel', async () => {
    vi.mocked(fetchRelationshipsOverview).mockResolvedValue({
      items: [
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
      ],
    })
    vi.mocked(fetchSurfaceTimeline).mockResolvedValue({ items: [] })
    vi.mocked(fetchPersonDetail).mockResolvedValue({
      person_id: 'alice',
      trust_history: [],
      shared_episodes_history: [],
      surface_counts: { resonant: 2, involuntary: 1, total: 3 },
    })

    render(<RelationshipsTab range={mockRange} />)

    await waitFor(() => {
      expect(screen.getByText('Alice')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Alice'))

    await waitFor(() => {
      expect(fetchPersonDetail).toHaveBeenCalledWith('alice', mockRange)
    })
    expect(screen.getByText(/alice — detail/i)).toBeInTheDocument()
  })

  it('closes detail panel when close button is clicked', async () => {
    vi.mocked(fetchRelationshipsOverview).mockResolvedValue({
      items: [
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
      ],
    })
    vi.mocked(fetchSurfaceTimeline).mockResolvedValue({ items: [] })
    vi.mocked(fetchPersonDetail).mockResolvedValue({
      person_id: 'alice',
      trust_history: [],
      shared_episodes_history: [],
      surface_counts: { resonant: 2, involuntary: 1, total: 3 },
    })

    render(<RelationshipsTab range={mockRange} />)

    await waitFor(() => {
      expect(screen.getByText('Alice')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Alice'))

    await waitFor(() => {
      expect(screen.getByText(/alice — detail/i)).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('close'))

    expect(screen.queryByText(/alice — detail/i)).not.toBeInTheDocument()
  })

  it('re-fetches person detail when range changes while a person is selected', async () => {
    vi.mocked(fetchRelationshipsOverview).mockResolvedValue({
      items: [
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
      ],
    })
    vi.mocked(fetchSurfaceTimeline).mockResolvedValue({ items: [] })
    vi.mocked(fetchPersonDetail).mockResolvedValue({
      person_id: 'alice',
      trust_history: [],
      shared_episodes_history: [],
      surface_counts: { resonant: 2, involuntary: 1, total: 3 },
    })

    const { rerender } = render(<RelationshipsTab range={mockRange} />)

    await waitFor(() => {
      expect(screen.getByText('Alice')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Alice'))

    await waitFor(() => {
      expect(fetchPersonDetail).toHaveBeenCalledTimes(1)
    })

    const newRange = {
      from: '2026-01-02T00:00:00+00:00',
      to: '2026-01-03T00:00:00+00:00',
    }
    rerender(<RelationshipsTab range={newRange} />)

    await waitFor(() => {
      expect(fetchPersonDetail).toHaveBeenCalledTimes(2)
    })
  })

  it('shows trust bar for person with trust_level', async () => {
    vi.mocked(fetchRelationshipsOverview).mockResolvedValue({
      items: [
        {
          person_id: 'alice',
          name: 'Alice',
          relation_kind: 'interlocutor',
          trust_level: 0.75,
          total_interactions: 10,
          shared_episodes_count: 3,
          last_interaction: '2026-01-01T12:00:00+00:00',
          first_interaction: '2026-01-01T10:00:00+00:00',
          aliases: [],
        },
      ],
    })
    vi.mocked(fetchSurfaceTimeline).mockResolvedValue({ items: [] })

    render(<RelationshipsTab range={mockRange} />)

    await waitFor(() => {
      expect(screen.getByText('75%')).toBeInTheDocument()
    })
  })

  it('shows dash for person without trust_level', async () => {
    vi.mocked(fetchRelationshipsOverview).mockResolvedValue({
      items: [
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
      ],
    })
    vi.mocked(fetchSurfaceTimeline).mockResolvedValue({ items: [] })

    render(<RelationshipsTab range={mockRange} />)

    await waitFor(() => {
      expect(screen.getByText('Bob')).toBeInTheDocument()
    })
    const dashes = screen.getAllByText('-')
    expect(dashes).toHaveLength(2)
  })

  it('shows aliases when available', async () => {
    vi.mocked(fetchRelationshipsOverview).mockResolvedValue({
      items: [
        {
          person_id: 'alice',
          name: 'Alice',
          relation_kind: 'interlocutor',
          trust_level: 0.8,
          total_interactions: 10,
          shared_episodes_count: 3,
          last_interaction: '2026-01-01T12:00:00+00:00',
          first_interaction: '2026-01-01T10:00:00+00:00',
          aliases: ['Alicia', 'Ali', 'Alice B.'],
        },
      ],
    })
    vi.mocked(fetchSurfaceTimeline).mockResolvedValue({ items: [] })

    render(<RelationshipsTab range={mockRange} />)

    await waitFor(() => {
      expect(screen.getByText(/also: Alicia, Ali/i)).toBeInTheDocument()
    })
  })

  it('shows truncated aliases when more than 2', async () => {
    vi.mocked(fetchRelationshipsOverview).mockResolvedValue({
      items: [
        {
          person_id: 'alice',
          name: 'Alice',
          relation_kind: 'interlocutor',
          trust_level: 0.8,
          total_interactions: 10,
          shared_episodes_count: 3,
          last_interaction: '2026-01-01T12:00:00+00:00',
          first_interaction: '2026-01-01T10:00:00+00:00',
          aliases: ['Alicia', 'Ali', 'Alice B.'],
        },
      ],
    })
    vi.mocked(fetchSurfaceTimeline).mockResolvedValue({ items: [] })

    render(<RelationshipsTab range={mockRange} />)

    await waitFor(() => {
      expect(screen.queryByText('Alice B.')).not.toBeInTheDocument()
    })
  })

  it('renders surface timeline chart title when data exists', async () => {
    vi.mocked(fetchRelationshipsOverview).mockResolvedValue({ items: [] })
    vi.mocked(fetchSurfaceTimeline).mockResolvedValue({
      items: [
        {
          ts: '2026-01-01T12:00:00+00:00',
          person_id: 'alice',
          surface_type: 'resonant',
        },
      ],
    })

    render(<RelationshipsTab range={mockRange} />)

    await waitFor(() => {
      expect(screen.getByText('Surface timeline')).toBeInTheDocument()
    })
  })

  it('renders SurfaceTimeline empty state with correct message', async () => {
    vi.mocked(fetchRelationshipsOverview).mockResolvedValue({ items: [] })
    vi.mocked(fetchSurfaceTimeline).mockResolvedValue({ items: [] })

    render(<RelationshipsTab range={mockRange} />)

    await waitFor(() => {
      expect(
        screen.getByText(/No surface events recorded/i),
      ).toBeInTheDocument()
    })
  })

  it('renders person overview card title', async () => {
    vi.mocked(fetchRelationshipsOverview).mockResolvedValue({ items: [] })
    vi.mocked(fetchSurfaceTimeline).mockResolvedValue({ items: [] })

    render(<RelationshipsTab range={mockRange} />)

    await waitFor(() => {
      expect(screen.getByText('Person overview')).toBeInTheDocument()
    })
  })
})
