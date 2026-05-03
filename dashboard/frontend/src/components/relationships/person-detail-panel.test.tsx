import { render, screen, fireEvent } from '@testing-library/react'

import { PersonDetailPanel } from '@/components/relationships/person-detail-panel'

const mockDetail = {
  person_id: 'alice',
  trust_history: [
    { ts: '2026-01-01T10:00:00+00:00', value: 0.5 },
    { ts: '2026-01-01T12:00:00+00:00', value: 0.7 },
    { ts: '2026-01-01T14:00:00+00:00', value: 0.8 },
  ],
  shared_episodes_history: [
    { ts: '2026-01-01T10:00:00+00:00', value: 1 },
    { ts: '2026-01-01T12:00:00+00:00', value: 2 },
    { ts: '2026-01-01T14:00:00+00:00', value: 3 },
  ],
  surface_counts: { resonant: 5, involuntary: 2, total: 7 },
}

describe('PersonDetailPanel', () => {
  it('renders trust level chart title', () => {
    render(<PersonDetailPanel detail={mockDetail} onClose={() => {}} />)
    expect(screen.getByText('Trust level')).toBeInTheDocument()
  })

  it('renders shared episodes chart title', () => {
    render(<PersonDetailPanel detail={mockDetail} onClose={() => {}} />)
    expect(screen.getByText('Shared episodes')).toBeInTheDocument()
  })

  it('renders surface frequency chart title', () => {
    render(<PersonDetailPanel detail={mockDetail} onClose={() => {}} />)
    expect(screen.getByText('Surface frequency')).toBeInTheDocument()
  })

  it('renders chart containers for all charts', () => {
    render(<PersonDetailPanel detail={mockDetail} onClose={() => {}} />)
    const chartContainers = document.querySelectorAll('[data-chart]')
    expect(chartContainers).toHaveLength(3)
  })

  it('renders close button', () => {
    const onClose = vi.fn()
    render(<PersonDetailPanel detail={mockDetail} onClose={onClose} />)

    expect(screen.getByText('close')).toBeInTheDocument()
    fireEvent.click(screen.getByText('close'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('renders person_id in title', () => {
    render(<PersonDetailPanel detail={mockDetail} onClose={() => {}} />)
    expect(screen.getByText(/alice — detail/i)).toBeInTheDocument()
  })

  it('shows no trust data when trust_history is empty', () => {
    const emptyDetail = { ...mockDetail, trust_history: [] }
    render(<PersonDetailPanel detail={emptyDetail} onClose={() => {}} />)

    expect(screen.getByText('No trust data')).toBeInTheDocument()
  })

  it('shows no episode data when shared_episodes_history is empty', () => {
    const emptyDetail = { ...mockDetail, shared_episodes_history: [] }
    render(<PersonDetailPanel detail={emptyDetail} onClose={() => {}} />)

    expect(screen.getByText('No episode data')).toBeInTheDocument()
  })

  it('shows no surface data when total is 0', () => {
    const emptyDetail = {
      ...mockDetail,
      surface_counts: { resonant: 0, involuntary: 0, total: 0 },
    }
    render(<PersonDetailPanel detail={emptyDetail} onClose={() => {}} />)

    expect(screen.getByText('No surface data')).toBeInTheDocument()
  })
})
