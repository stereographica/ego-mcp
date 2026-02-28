import { useMemo, useState } from 'react'

import { HistoryTab } from '@/components/history/history-tab'
import { DashboardHeader } from '@/components/layout/dashboard-header'
import { TimeRangeControls } from '@/components/layout/time-range-controls'
import { LogsTab } from '@/components/logs/logs-tab'
import { NowTab } from '@/components/now/now-tab'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useDashboardSocket } from '@/hooks/use-dashboard-socket'
import type { DateRange, TimeRangePreset } from '@/types'

const makeRange = (preset: TimeRangePreset): DateRange => {
  const to = new Date()
  const from = new Date(to)
  const map: Record<Exclude<TimeRangePreset, 'custom'>, number> = {
    '15m': 15,
    '1h': 60,
    '6h': 360,
    '24h': 1440,
    '7d': 10080,
  }
  from.setMinutes(
    from.getMinutes() - map[preset as Exclude<TimeRangePreset, 'custom'>],
  )
  return { from: from.toISOString(), to: to.toISOString() }
}

const App = () => {
  const [activeTab, setActiveTab] = useState('now')
  const [preset, setPreset] = useState<TimeRangePreset>('1h')
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo] = useState('')

  const { current, logLines, connected } = useDashboardSocket()

  const range = useMemo<DateRange>(() => {
    if (preset !== 'custom') return makeRange(preset)
    return {
      from: customFrom
        ? new Date(customFrom).toISOString()
        : new Date(Date.now() - 3600_000).toISOString(),
      to: customTo
        ? new Date(customTo).toISOString()
        : new Date().toISOString(),
    }
  }, [preset, customFrom, customTo])

  return (
    <main className="mx-auto w-[min(1680px,calc(100vw-24px))] p-6">
      <DashboardHeader current={current} connected={connected} />

      <Tabs className="mt-4" value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="now">Now</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
          <TabsTrigger value="logs">Logs</TabsTrigger>
        </TabsList>

        {activeTab !== 'now' && (
          <div className="mt-3">
            <TimeRangeControls
              preset={preset}
              onPresetChange={setPreset}
              customFrom={customFrom}
              customTo={customTo}
              onCustomFromChange={setCustomFrom}
              onCustomToChange={setCustomTo}
            />
          </div>
        )}

        <TabsContent value="now">
          <NowTab current={current} logLines={logLines} />
        </TabsContent>

        <TabsContent value="history">
          <HistoryTab range={range} preset={preset} />
        </TabsContent>

        <TabsContent value="logs">
          <LogsTab
            range={range}
            preset={preset}
            isActive={activeTab === 'logs'}
          />
        </TabsContent>
      </Tabs>
    </main>
  )
}

export default App
