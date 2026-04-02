import { render, screen } from '@testing-library/react'

import { fetchNotionHistory } from '@/api'
import { MemoryDetailPanel } from '@/components/memory/memory-detail-panel'
import { NotionDetailPanel } from '@/components/memory/notion-detail-panel'

vi.mock('@/api', () => ({
  fetchNotionHistory: vi.fn().mockResolvedValue([]),
}))

describe('MemoryDetailPanel', () => {
  it('renders detailed memory content and links', () => {
    render(
      <MemoryDetailPanel
        detail={{
          id: 'mem-1',
          content: 'Detailed memory body',
          timestamp: '2026-01-01T12:00:00Z',
          category: 'technical',
          importance: 4,
          tags: ['design', 'db'],
          is_private: false,
          access_count: 14,
          last_accessed: '2026-01-02T12:00:00Z',
          decay: 0.82,
          emotional_trace: {
            valence: 0.42,
            arousal: 0.65,
            intensity: 0.55,
          },
          linked_ids: [
            {
              target_id: 'mem-2',
              link_type: 'caused_by',
              confidence: 0.91,
              note: '',
            },
          ],
          generated_notion_ids: ['notion-1'],
        }}
      />,
    )

    expect(screen.getByText('Detailed memory body')).toBeInTheDocument()
    expect(screen.getByText('#design')).toBeInTheDocument()
    expect(screen.getByText('mem-2')).toBeInTheDocument()
    expect(screen.getByText('notion-1')).toBeInTheDocument()
  })
})

describe('NotionDetailPanel', () => {
  it('renders notion detail information', async () => {
    vi.mocked(fetchNotionHistory).mockResolvedValue([])

    render(
      <NotionDetailPanel
        notion={{
          id: 'notion-1',
          label: 'Technical growth',
          category: 'notion',
          is_notion: true,
          tags: ['design'],
          degree: 4,
          betweenness: 0.2,
          confidence: 0.87,
          reinforcement_count: 12,
          source_count: 8,
          is_conviction: true,
          person_id: 'Master',
          created: '2026-01-02T12:00:00Z',
          last_reinforced: '2026-01-04T12:00:00Z',
          related_count: 2,
        }}
        relatedNotionIds={['notion-2', 'notion-3']}
        sourceMemoryIds={['mem-1', 'mem-2']}
      />,
    )

    expect(screen.getByText('Technical growth')).toBeInTheDocument()
    expect(screen.getByText('Confidence')).toBeInTheDocument()
    expect(await screen.findByText(/notion-2/)).toBeInTheDocument()
    expect(screen.getByText(/mem-1/)).toBeInTheDocument()
  })
})
