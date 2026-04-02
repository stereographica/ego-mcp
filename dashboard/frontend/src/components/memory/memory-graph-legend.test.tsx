import { render, screen } from '@testing-library/react'

import { MemoryGraphLegend } from '@/components/memory/memory-graph-legend'

describe('MemoryGraphLegend', () => {
  it('renders node and edge legend items', () => {
    render(<MemoryGraphLegend categories={['TECHNICAL', 'DAILY']} />)

    expect(screen.getByText('Legend')).toBeInTheDocument()
    expect(screen.getByText('Memory node')).toBeInTheDocument()
    expect(screen.getByText('Notion node')).toBeInTheDocument()
    expect(screen.getByText('Conviction')).toBeInTheDocument()
    expect(screen.getByText('TECHNICAL')).toBeInTheDocument()
    expect(screen.getByText('DAILY')).toBeInTheDocument()
    expect(screen.getByText('Memory → Notion')).toBeInTheDocument()
  })
})
