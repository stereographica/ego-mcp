import { useEffect, useState } from 'react'

import { fetchUsage } from '@/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useTimestampFormatter } from '@/hooks/use-timestamp-formatter'
import type { DateRange, UsagePoint } from '@/types'

const sumToolCalls = (rows: UsagePoint[]) =>
  rows.reduce((sum, row) => {
    const rowTotal = Object.entries(row).reduce((rowSum, [key, value]) => {
      if (key === 'ts' || typeof value !== 'number') return rowSum
      return rowSum + value
    }, 0)
    return sum + rowTotal
  }, 0)

const localDayRanges = (): { today: DateRange; yesterday: DateRange } => {
  const now = new Date()
  const startOfToday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  )
  const startOfYesterday = new Date(startOfToday)
  startOfYesterday.setDate(startOfYesterday.getDate() - 1)
  const endOfYesterday = new Date(startOfToday.getTime() - 1)

  return {
    today: {
      from: startOfToday.toISOString(),
      to: now.toISOString(),
    },
    yesterday: {
      from: startOfYesterday.toISOString(),
      to: endOfYesterday.toISOString(),
    },
  }
}

export const SessionSummary = () => {
  const [todayToolCalls, setTodayToolCalls] = useState(0)
  const [yesterdayToolCalls, setYesterdayToolCalls] = useState(0)
  const { clientTimeZone } = useTimestampFormatter()

  useEffect(() => {
    let disposed = false

    const loadToolCallTotals = async () => {
      const { today, yesterday } = localDayRanges()
      const [todayRows, yesterdayRows] = await Promise.all([
        fetchUsage(today, '15m'),
        fetchUsage(yesterday, '15m'),
      ])
      if (disposed) return
      setTodayToolCalls(sumToolCalls(todayRows))
      setYesterdayToolCalls(sumToolCalls(yesterdayRows))
    }

    void loadToolCallTotals()
    const timer = setInterval(loadToolCallTotals, 60_000)

    return () => {
      disposed = true
      clearInterval(timer)
    }
  }, [])

  return (
    <div className="space-y-2">
      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-muted-foreground text-xs font-medium">
              tool calls (today)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{todayToolCalls}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-muted-foreground text-xs font-medium">
              tool calls (yesterday)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{yesterdayToolCalls}</p>
          </CardContent>
        </Card>
      </div>
      <p className="text-muted-foreground text-xs">
        Timezone: {clientTimeZone}
      </p>
    </div>
  )
}
