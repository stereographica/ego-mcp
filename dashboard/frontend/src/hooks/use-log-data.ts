import { useEffect, useState } from 'react'

import { fetchLogs } from '@/api'
import type { DateRange, LogPoint } from '@/types'

export const useLogData = (
  enabled: boolean,
  range: DateRange,
  logLevel: string,
  loggerFilter: string,
) => {
  const [logs, setLogs] = useState<LogPoint[]>([])

  useEffect(() => {
    if (!enabled) return

    let disposed = false
    const loadLogs = async () => {
      const data = await fetchLogs(range, logLevel, loggerFilter)
      if (!disposed) {
        setLogs(data)
      }
    }
    void loadLogs()
    const timer = setInterval(loadLogs, 2000)
    return () => {
      disposed = true
      clearInterval(timer)
    }
  }, [enabled, range, logLevel, loggerFilter])

  return logs
}
