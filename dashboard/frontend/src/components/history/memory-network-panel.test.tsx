import { render, screen } from '@testing-library/react'

import { MemoryNetworkPanel } from '@/components/history/memory-network-panel'

describe('MemoryNetworkPanel', () => {
  it('renders network summary and node list', () => {
    const { container } = render(
      <MemoryNetworkPanel
        network={{
          nodes: [
            {
              id: 'mem-1',
              label: 'Memory one',
              category: 'memory',
              is_notion: false,
              access_count: 3,
              decay: 0.8,
            },
            {
              id: 'notion-1',
              label: 'Notion one',
              category: 'notion',
              is_notion: true,
              confidence: 0.9,
              access_count: 2,
              reinforcement_count: 6,
              person_id: 'Master',
              related_count: 1,
              is_conviction: true,
            },
          ],
          edges: [
            {
              source: 'notion-1',
              target: 'mem-1',
              link_type: 'notion_source',
              confidence: 0.9,
            },
            {
              source: 'notion-1',
              target: 'notion-2',
              link_type: 'notion_related',
              confidence: 0.7,
            },
          ],
        }}
      />,
    )

    expect(screen.getByText('Memory network')).toBeInTheDocument()
    expect(screen.getByText('Memory one')).toBeInTheDocument()
    expect(screen.getAllByText('Notion one')).toHaveLength(2)
    expect(screen.getByText('nodes 2')).toBeInTheDocument()
    expect(screen.getByText('notion links 1')).toBeInTheDocument()
    expect(screen.getByText(/conviction/)).toBeInTheDocument()
    expect(screen.getByText(/person Master/)).toBeInTheDocument()
    expect(container.firstChild).toHaveClass('min-w-0', 'overflow-hidden')
    expect(
      screen.getByRole('img', { name: 'Memory network graph' }),
    ).toHaveClass('max-w-full')
  })
})
