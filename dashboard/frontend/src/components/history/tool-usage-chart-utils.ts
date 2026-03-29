type TooltipPayloadItem = {
  dataKey?: string | number
  type?: string
  value?: unknown
}

export const shouldShowToolUsageTooltip = (
  payload: TooltipPayloadItem[] | undefined,
  visibleKeys: string[],
) =>
  (payload ?? []).some((item) => {
    if (item.type === 'none') return false

    const key = `${item.dataKey ?? ''}`
    if (key.length > 0 && !visibleKeys.includes(key)) {
      return false
    }

    return typeof item.value === 'number'
      ? item.value !== 0
      : item.value !== null && item.value !== undefined
  })
