import { useEffect, useRef, useState } from 'react'

import { fetchLogs } from '@/api'
import type { DateRange, LogPoint, TimeRangePreset } from '@/types'

const PRESET_MINUTES: Record<Exclude<TimeRangePreset, 'custom'>, number> = {
  '15m': 15,
  '1h': 60,
  '6h': 360,
  '24h': 1440,
  '7d': 10080,
}

export const useLogData = (
  enabled: boolean,
  preset: TimeRangePreset,
  range: DateRange,
  logLevel: string,
  searchFilter: string,
) => {
  const [logs, setLogs] = useState<LogPoint[]>([])
  const rangeRef = useRef(range)
  rangeRef.current = range

  useEffect(() => {
    if (!enabled) return

    let disposed = false
    const loadLogs = async () => {
      // For presets, compute a fresh range on every poll so the window
      // always ends at "now" and new logs are not excluded.
      let currentRange: DateRange
      if (preset === 'custom') {
        currentRange = rangeRef.current
      } else {
        const to = new Date()
        const from = new Date(to)
        from.setMinutes(from.getMinutes() - PRESET_MINUTES[preset])
        currentRange = { from: from.toISOString(), to: to.toISOString() }
      }
      const data = await fetchLogs(currentRange, logLevel, searchFilter)
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
  }, [enabled, preset, logLevel, searchFilter])

  return logs
}
