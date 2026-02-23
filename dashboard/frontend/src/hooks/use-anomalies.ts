import { useEffect, useState } from 'react'

import { fetchAnomalies } from '@/api'
import type { AnomalyAlert } from '@/types'

export const useAnomalies = (): AnomalyAlert[] => {
  const [alerts, setAlerts] = useState<AnomalyAlert[]>([])

  useEffect(() => {
    let disposed = false

    const load = async () => {
      const now = new Date()
      const from = new Date(now.getTime() - 3600_000)
      const range = { from: from.toISOString(), to: now.toISOString() }
      const data = await fetchAnomalies(range, '1m')
      if (!disposed) setAlerts(data)
    }

    void load()
    const timer = setInterval(load, 30_000)
    return () => {
      disposed = true
      clearInterval(timer)
    }
  }, [])

  return alerts
}
