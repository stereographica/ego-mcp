import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { MemoryTab } from '@/components/memory/memory-tab'
import { useMemoryNetwork } from '@/hooks/use-memory-network'
import type { MemoryDetail, MemoryNetworkResponse } from '@/types'

vi.mock('@/hooks/use-memory-network', () => ({
  useMemoryNetwork: vi.fn(),
}))

vi.mock('@/components/memory/memory-graph', () => ({
  MemoryGraph: ({
    network,
    onSelectNode,
  }: {
    network: MemoryNetworkResponse
    onSelectNode: (node: MemoryNetworkResponse['nodes'][number]) => void
  }) => (
    <div>
      <p>Graph mock</p>
      {network.nodes.map((node) => (
        <button key={node.id} type="button" onClick={() => onSelectNode(node)}>
          {node.label ?? node.id}
        </button>
      ))}
    </div>
  ),
}))

const network: MemoryNetworkResponse = {
  nodes: [
    {
      id: 'mem-1',
      label: 'Memory one',
      category: 'TECHNICAL',
      is_notion: false,
      content_preview: 'Designing the memory tab',
      importance: 4,
      access_count: 7,
      decay: 0.82,
      degree: 3,
      betweenness: 0.14,
    },
    {
      id: 'notion-1',
      label: 'Memory systems',
      category: 'notion',
      is_notion: true,
      confidence: 0.91,
      reinforcement_count: 6,
      source_count: 1,
      degree: 2,
      betweenness: 0.2,
      is_conviction: true,
    },
  ],
  edges: [
    {
      source: 'mem-1',
      target: 'notion-1',
      link_type: 'notion_source',
      confidence: 0.9,
    },
  ],
  stats: {
    node_count: 2,
    memory_count: 1,
    notion_count: 1,
    edge_count: 1,
    conviction_count: 1,
    avg_memory_decay: 0.82,
    graph_density: 1,
    top_hub_id: 'mem-1',
    top_hub_degree: 3,
    top_category: 'TECHNICAL',
    top_category_ratio: 1,
  },
}

const detail: MemoryDetail = {
  id: 'mem-1',
  content: 'Detailed memory body',
  timestamp: '2026-01-01T12:00:00Z',
  category: 'TECHNICAL',
  importance: 4,
  tags: ['design'],
  is_private: false,
  access_count: 7,
  last_accessed: '2026-01-01T13:00:00Z',
  decay: 0.82,
  emotional_trace: {
    valence: 0.4,
    arousal: 0.6,
    intensity: 0.5,
  },
  linked_ids: [],
  generated_notion_ids: ['notion-1'],
}

describe('MemoryTab', () => {
  it('renders graph controls and opens detail for a selected memory', async () => {
    const user = userEvent.setup()
    const loadDetail = vi.fn().mockResolvedValue(detail)
    vi.mocked(useMemoryNetwork).mockReturnValue({
      fullNetwork: network,
      network,
      loading: false,
      path: {
        node_ids: [],
        edge_pairs: [],
        length: 0,
        exists: false,
      },
      loadFullGraph: vi.fn(),
      loadSubgraph: vi.fn(),
      loadDetail,
      loadPath: vi.fn(),
      clearPath: vi.fn(),
    })

    render(<MemoryTab isActive />)

    expect(screen.getByText('Memory graph')).toBeInTheDocument()
    expect(screen.getByText('Filter panel')).toBeInTheDocument()
    expect(screen.getByText('Graph stats')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Memory one' }))

    expect(loadDetail).toHaveBeenCalledWith('mem-1')
    expect(await screen.findByText('Memory detail')).toBeInTheDocument()
    expect(screen.getByText('Detailed memory body')).toBeInTheDocument()
  })
})
