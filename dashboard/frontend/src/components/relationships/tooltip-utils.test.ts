import { formatTooltipTimestampLabel } from '@/components/relationships/tooltip-utils'

describe('formatTooltipTimestampLabel', () => {
  it('formats ISO timestamps with the provided formatter', () => {
    expect(
      formatTooltipTimestampLabel(
        '2026-01-01T12:00:00Z',
        (value) => `formatted:${value}`,
      ),
    ).toBe('formatted:2026-01-01T12:00:00Z')
  })

  it('falls back to a string when the label is not a timestamp', () => {
    expect(formatTooltipTimestampLabel(undefined, () => 'unused')).toBe('')
    expect(formatTooltipTimestampLabel(42, () => 'unused')).toBe('42')
  })
})
