import {
  applyMemoryGraphFilters,
  calcMemoryNodeRadius,
  calcNotionNodeRadius,
} from '@/components/memory/memory-graph-utils'
import type { MemoryGraphFilters, MemoryNetworkResponse } from '@/types'

const defaultFilters: MemoryGraphFilters = {
  showMemories: true,
  showNotions: true,
  convictionsOnly: false,
  categories: [],
  minImportance: 1,
  minConfidence: 0,
  minDecay: 0,
}

describe('memory-graph-utils', () => {
  it('clamps memory node radius at the minimum size', () => {
    expect(
      calcMemoryNodeRadius({
        id: 'mem-1',
        category: 'daily',
        is_notion: false,
        tags: [],
        degree: 0,
        betweenness: 0,
        importance: 1,
        access_count: 0,
        decay: 0,
      }),
    ).toBe(8)
  })

  it('clamps notion node radius at the maximum size', () => {
    expect(
      calcNotionNodeRadius({
        id: 'notion-1',
        label: 'Conviction',
        category: 'notion',
        is_notion: true,
        tags: [],
        degree: 30,
        betweenness: 0.5,
        confidence: 1,
        reinforcement_count: 20,
        source_count: 10,
      }),
    ).toBe(40)
  })

  it('filters out memory nodes when showMemories is false', () => {
    const network: MemoryNetworkResponse = {
      nodes: [
        {
          id: 'mem-1',
          label: 'Memory',
          category: 'technical',
          is_notion: false,
          tags: ['db'],
          degree: 1,
          betweenness: 0,
          importance: 3,
          decay: 0.8,
          access_count: 4,
        },
        {
          id: 'notion-1',
          label: 'Notion',
          category: 'notion',
          is_notion: true,
          tags: ['db'],
          degree: 1,
          betweenness: 0,
          confidence: 0.85,
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
          confidence: 0.8,
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
        top_hub_degree: 1,
        top_category: 'technical',
        top_category_ratio: 1,
      },
    }

    const filtered = applyMemoryGraphFilters(network, {
      ...defaultFilters,
      showMemories: false,
    })

    expect(filtered.nodes.map((node) => node.id)).toEqual(['notion-1'])
    expect(filtered.edges).toEqual([])
  })
})
