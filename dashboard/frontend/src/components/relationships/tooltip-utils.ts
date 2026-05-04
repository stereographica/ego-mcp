export const formatTooltipTimestampLabel = (
  label: unknown,
  formatTs: (value: string) => string,
) => {
  if (typeof label === 'string' && label.length > 0) {
    return formatTs(label)
  }

  return String(label ?? '')
}
