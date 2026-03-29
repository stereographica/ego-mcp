import { shouldShowToolUsageTooltip } from '@/components/history/tool-usage-chart-utils'

describe('shouldShowToolUsageTooltip', () => {
  it('returns false when every visible series is zero', () => {
    expect(
      shouldShowToolUsageTooltip(
        [
          { dataKey: 'read_file', type: 'line', value: 0 },
          { dataKey: 'write_file', type: 'line', value: 0 },
        ],
        ['read_file', 'write_file'],
      ),
    ).toBe(false)
  })

  it('returns true when any visible series has a non-zero value', () => {
    expect(
      shouldShowToolUsageTooltip(
        [
          { dataKey: 'read_file', type: 'line', value: 0 },
          { dataKey: 'write_file', type: 'line', value: 2 },
        ],
        ['read_file', 'write_file'],
      ),
    ).toBe(true)
  })

  it('ignores hidden series values', () => {
    expect(
      shouldShowToolUsageTooltip(
        [
          { dataKey: 'read_file', type: 'line', value: 0 },
          { dataKey: 'write_file', type: 'line', value: 3 },
        ],
        ['read_file'],
      ),
    ).toBe(false)
  })
})
