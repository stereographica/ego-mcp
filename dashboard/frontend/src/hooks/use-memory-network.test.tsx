import { act, renderHook, waitFor } from '@testing-library/react'

import * as api from '@/api'
import { useMemoryNetwork } from '@/hooks/use-memory-network'
import type { MemoryDetail, MemoryNetworkResponse } from '@/types'

vi.mock('@/api', () => ({
  fetchMemoryDetail: vi.fn(),
  fetchMemoryNetwork: vi.fn(),
  fetchNotions: vi.fn(),
  fetchMemoryPath: vi.fn(),
  fetchMemorySubgraph: vi.fn(),
}))

const network: MemoryNetworkResponse = {
  nodes: [
    {
      id: 'mem-1',
      label: 'Memory one',
      category: 'TECHNICAL',
      is_notion: false,
      degree: 2,
      betweenness: 0.1,
      importance: 4,
      access_count: 3,
      decay: 0.8,
    },
    {
      id: 'notion-1',
      label: 'Technical growth',
      category: 'notion',
      is_notion: true,
      degree: 1,
      betweenness: 0,
      confidence: 0.91,
      reinforcement_count: 6,
      source_count: 1,
      is_conviction: true,
    },
  ],
  edges: [
    {
      source: 'mem-1',
      target: 'notion-1',
      link_type: 'notion_source',
      confidence: 0.91,
    },
  ],
  stats: {
    node_count: 2,
    memory_count: 1,
    notion_count: 1,
    edge_count: 1,
    conviction_count: 1,
    avg_memory_decay: 0.8,
    graph_density: 1,
    top_hub_id: 'mem-1',
    top_hub_degree: 2,
    top_category: 'TECHNICAL',
    top_category_ratio: 1,
  },
}

const subgraph: MemoryNetworkResponse = {
  ...network,
  nodes: [network.nodes[0]],
  edges: [],
  stats: {
    ...network.stats,
    node_count: 1,
    notion_count: 0,
    edge_count: 0,
    conviction_count: 0,
    graph_density: 0,
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
  access_count: 3,
  last_accessed: '2026-01-01T13:00:00Z',
  decay: 0.8,
  emotional_trace: {
    valence: 0.4,
    arousal: 0.5,
    intensity: 0.6,
  },
  linked_ids: [],
  generated_notion_ids: ['notion-1'],
}

describe('useMemoryNetwork', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('loads the full graph when active and exposes subgraph/detail/path actions', async () => {
    vi.mocked(api.fetchMemoryNetwork).mockResolvedValue(network)
    vi.mocked(api.fetchNotions).mockResolvedValue({ items: [] })
    vi.mocked(api.fetchMemorySubgraph).mockResolvedValue(subgraph)
    vi.mocked(api.fetchMemoryDetail).mockResolvedValue(detail)
    vi.mocked(api.fetchMemoryPath).mockResolvedValue({
      node_ids: ['mem-1', 'notion-1'],
      edge_pairs: [['mem-1', 'notion-1']],
      length: 1,
      exists: true,
    })

    const { result } = renderHook(() => useMemoryNetwork(true))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.network).toEqual(network)

    await act(async () => {
      await result.current.loadSubgraph('mem-1', 2)
    })
    expect(api.fetchMemorySubgraph).toHaveBeenCalledWith('mem-1', 2)
    expect(result.current.network).toEqual(subgraph)

    await act(async () => {
      await result.current.loadFullGraph()
    })
    expect(result.current.network).toEqual(network)

    await expect(result.current.loadDetail('mem-1')).resolves.toEqual(detail)
    expect(api.fetchMemoryDetail).toHaveBeenCalledWith('mem-1')

    await act(async () => {
      await result.current.loadPath('mem-1', 'notion-1')
    })
    expect(result.current.path).toEqual({
      node_ids: ['mem-1', 'notion-1'],
      edge_pairs: [['mem-1', 'notion-1']],
      length: 1,
      exists: true,
    })

    act(() => {
      result.current.clearPath()
    })
    expect(result.current.path).toEqual({
      node_ids: [],
      edge_pairs: [],
      length: 0,
      exists: false,
    })
  })

  it('does not load until the memory tab is active', () => {
    renderHook(() => useMemoryNetwork(false))

    expect(api.fetchMemoryNetwork).not.toHaveBeenCalled()
    expect(api.fetchNotions).not.toHaveBeenCalled()
  })
})
