import { useMemo } from 'react'

const browserTimeZone = () => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

const makeTimestampFormatter = (timeZone: string) =>
  new Intl.DateTimeFormat(undefined, {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })

export const formatTimestamp = (
  value: string,
  formatter: Intl.DateTimeFormat,
) => {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return formatter.format(parsed)
}

export const useTimestampFormatter = () => {
  const clientTimeZone = useMemo(() => browserTimeZone(), [])
  const formatter = useMemo(
    () => makeTimestampFormatter(clientTimeZone),
    [clientTimeZone],
  )
  const formatTs = (value: string) => formatTimestamp(value, formatter)
  return { formatTs, clientTimeZone }
}
