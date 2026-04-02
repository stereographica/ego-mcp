import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { MemoryFilterPanel } from '@/components/memory/memory-filter-panel'
import type { MemoryGraphFilters } from '@/types'

const filters: MemoryGraphFilters = {
  showMemories: true,
  showNotions: true,
  convictionsOnly: false,
  categories: [],
  minImportance: 1,
  minConfidence: 0,
  minDecay: 0,
}

describe('MemoryFilterPanel', () => {
  it('calls onChange when filters are updated and when reset is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(
      <MemoryFilterPanel
        filters={filters}
        categories={['technical', 'daily']}
        onChange={onChange}
      />,
    )

    await user.click(screen.getByLabelText('Memories'))
    expect(onChange).toHaveBeenCalledWith({
      ...filters,
      showMemories: false,
    })

    await user.click(screen.getByLabelText('Category technical'))
    expect(onChange).toHaveBeenCalledWith({
      ...filters,
      categories: ['technical'],
    })

    await user.click(screen.getByRole('button', { name: 'Reset filters' }))
    expect(onChange).toHaveBeenLastCalledWith(filters)
  })
})
