import { render, screen, waitFor } from '@testing-library/react'

import * as api from '@/api'
import { NotionPanel } from '@/components/history/notion-panel'

vi.mock('@/api', () => ({
  fetchNotionHistory: vi.fn(),
}))

describe('NotionPanel', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders notion confidence rows and fetches selected notion history', async () => {
    vi.mocked(api.fetchNotionHistory).mockResolvedValue([
      { ts: '2026-01-01T11:00:00Z', value: 0.6 },
      { ts: '2026-01-01T12:00:00Z', value: 0.82 },
    ])

    const { container } = render(
      <NotionPanel
        notions={[
          {
            id: 'notion-1',
            label: 'Pattern seeking',
            emotion_tone: 'curious',
            confidence: 0.82,
            source_count: 3,
            source_memory_ids: ['mem-1'],
            related_notion_ids: ['notion-2', 'notion-3'],
            related_count: 2,
            reinforcement_count: 5,
            person_id: 'Master',
            is_conviction: true,
            created: '2026-01-01T11:00:00Z',
            last_reinforced: '2026-01-01T12:00:00Z',
          },
        ]}
        range={{
          from: '2026-01-01T11:00:00Z',
          to: '2026-01-01T12:00:00Z',
        }}
        preset="custom"
      />,
    )

    expect(screen.getByText('Notions')).toBeInTheDocument()
    expect(screen.getAllByText('Pattern seeking')).toHaveLength(2)
    expect(screen.getAllByText('82%').length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText('conviction').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Master').length).toBeGreaterThanOrEqual(1)
    expect(
      screen.getAllByText('reinforcement 5').length,
    ).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('notion-2, notion-3')).toBeInTheDocument()
    expect(container.firstChild).toHaveClass('min-w-0', 'overflow-hidden')

    await waitFor(() => {
      expect(api.fetchNotionHistory).toHaveBeenCalledWith(
        'notion-1',
        {
          from: '2026-01-01T11:00:00Z',
          to: '2026-01-01T12:00:00Z',
        },
        '15m',
      )
    })

    await waitFor(() => {
      expect(
        screen.getByRole('img', { name: 'Selected notion confidence trend' }),
      ).toBeInTheDocument()
    })
  })
})
