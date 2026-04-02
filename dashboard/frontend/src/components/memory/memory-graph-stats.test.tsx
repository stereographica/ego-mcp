import { render, screen } from '@testing-library/react'

import { MemoryGraphStats } from '@/components/memory/memory-graph-stats'

describe('MemoryGraphStats', () => {
  it('renders the graph summary cards', () => {
    render(
      <MemoryGraphStats
        stats={{
          node_count: 12,
          memory_count: 9,
          notion_count: 3,
          edge_count: 18,
          conviction_count: 2,
          avg_memory_decay: 0.71,
          graph_density: 0.28,
          top_hub_id: 'mem-2',
          top_hub_degree: 5,
          top_category: 'technical',
          top_category_ratio: 0.56,
        }}
      />,
    )

    expect(screen.getByText('Nodes')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByText('Top hub')).toBeInTheDocument()
    expect(screen.getByText('mem-2 (5)')).toBeInTheDocument()
    expect(screen.getByText('technical (56%)')).toBeInTheDocument()
    expect(screen.getByText('Density')).toBeInTheDocument()
    expect(screen.getByText('0.280')).toBeInTheDocument()
  })
})
