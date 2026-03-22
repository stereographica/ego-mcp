import { render, screen } from '@testing-library/react'

import { MemoryNetworkPanel } from '@/components/history/memory-network-panel'

describe('MemoryNetworkPanel', () => {
  it('renders network summary and node list', () => {
    render(
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
            },
          ],
          edges: [
            {
              source: 'notion-1',
              target: 'mem-1',
              link_type: 'notion_source',
              confidence: 0.9,
            },
          ],
        }}
      />,
    )

    expect(screen.getByText('Memory network')).toBeInTheDocument()
    expect(screen.getByText('Memory one')).toBeInTheDocument()
    expect(screen.getAllByText('Notion one')).toHaveLength(2)
    expect(screen.getByText('nodes 2')).toBeInTheDocument()
  })
})
