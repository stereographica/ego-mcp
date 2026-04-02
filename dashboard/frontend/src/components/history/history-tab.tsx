import { DesireHistoryChart } from '@/components/history/desire-history-chart'
import { EmotionDistributionChart } from '@/components/history/emotion-distribution-chart'
import { EmotionTimelineChart } from '@/components/history/emotion-timeline-chart'
import { IntensityChart } from '@/components/history/intensity-chart'
import { NotionPanel } from '@/components/history/notion-panel'
import { ToolUsageChart } from '@/components/history/tool-usage-chart'
import { ValenceArousalChart } from '@/components/history/valence-arousal-chart'
import { useHistoryData } from '@/hooks/use-history-data'
import type { DateRange, DesireCatalogItem, TimeRangePreset } from '@/types'

type HistoryTabProps = {
  range: DateRange
  preset: TimeRangePreset
  desireCatalog: DesireCatalogItem[]
}

export const HistoryTab = ({
  range,
  preset,
  desireCatalog,
}: HistoryTabProps) => {
  const {
    intensity,
    usage,
    timeline,
    valence,
    arousal,
    emotionTrend,
    emotionHeatmap,
    historyMarkers,
    notions,
    toolSeriesKeys,
    desireKeys,
    desireChartData,
  } = useHistoryData('history', range, preset, desireCatalog)

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
      <div className="[&>*]:min-w-0">
        <NotionPanel notions={notions} range={range} preset={preset} />
      </div>
      <DesireHistoryChart
        desireChartData={desireChartData}
        desireKeys={desireKeys}
        desireCatalog={desireCatalog}
        markers={historyMarkers}
      />
    </div>
  )
}
