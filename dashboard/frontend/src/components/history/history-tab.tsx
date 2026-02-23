import { DesireHistoryChart } from '@/components/history/desire-history-chart'
import { IntensityChart } from '@/components/history/intensity-chart'
import { ToolUsageChart } from '@/components/history/tool-usage-chart'
import { ValenceArousalChart } from '@/components/history/valence-arousal-chart'
import { useHistoryData } from '@/hooks/use-history-data'
import type { DateRange, TimeRangePreset } from '@/types'

type HistoryTabProps = {
  range: DateRange
  preset: TimeRangePreset
}

export const HistoryTab = ({ range, preset }: HistoryTabProps) => {
  const {
    intensity,
    usage,
    timeline,
    valence,
    arousal,
    toolSeriesKeys,
    desireChartData,
  } = useHistoryData('history', range, preset)

  return (
    <div className="space-y-4">
      <ToolUsageChart
        usage={usage}
        toolSeriesKeys={toolSeriesKeys}
        timeline={timeline}
      />
      <IntensityChart intensity={intensity} />
      <ValenceArousalChart valence={valence} arousal={arousal} />
      <DesireHistoryChart desireChartData={desireChartData} />
    </div>
  )
}
