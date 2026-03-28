import { DesireHistoryChart } from '@/components/history/desire-history-chart'
import { EmotionDistributionChart } from '@/components/history/emotion-distribution-chart'
import { EmotionTimelineChart } from '@/components/history/emotion-timeline-chart'
import { IntensityChart } from '@/components/history/intensity-chart'
import { MemoryNetworkPanel } from '@/components/history/memory-network-panel'
import { NotionPanel } from '@/components/history/notion-panel'
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
    emotionTrend,
    emotionHeatmap,
    historyMarkers,
    memoryNetwork,
    notions,
    toolSeriesKeys,
    desireKeys,
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
      <EmotionTimelineChart points={emotionTrend} markers={historyMarkers} />
      <EmotionDistributionChart heatmapData={emotionHeatmap} />
      <ValenceArousalChart valence={valence} arousal={arousal} />
      <div className="grid gap-4 xl:grid-cols-2 [&>*]:min-w-0">
        <MemoryNetworkPanel network={memoryNetwork} />
        <NotionPanel notions={notions} />
      </div>
      <DesireHistoryChart
        desireChartData={desireChartData}
        desireKeys={desireKeys}
        markers={historyMarkers}
      />
    </div>
  )
}
