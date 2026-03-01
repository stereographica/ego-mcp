import { useEffect, useMemo, useState } from 'react'

import {
  fetchArousal,
  fetchIntensity,
  fetchMetric,
  fetchStringHeatmap,
  fetchStringTimeline,
  fetchTimeline,
  fetchUsage,
  fetchValence,
} from '@/api'
import { DESIRE_METRIC_KEYS, type DesireMetricKey } from '@/constants'
import type {
  DateRange,
  HeatmapPoint,
  IntensityPoint,
  SeriesPoint,
  StringPoint,
  TimeRangePreset,
  UsagePoint,
} from '@/types'

type DesireMetricSeriesMap = Record<DesireMetricKey, SeriesPoint[]>

const makeEmptyDesireMetricSeriesMap = (): DesireMetricSeriesMap => ({
  information_hunger: [],
  social_thirst: [],
  cognitive_coherence: [],
  pattern_seeking: [],
  predictability: [],
  recognition: [],
  resonance: [],
  expression: [],
  curiosity: [],
})

const bucketFor = (preset: TimeRangePreset) =>
  preset === '15m' || preset === '1h' ? '1m' : '5m'

export const useHistoryData = (
  activeTab: string,
  range: DateRange,
  preset: TimeRangePreset,
) => {
  const [intensity, setIntensity] = useState<IntensityPoint[]>([])
  const [usage, setUsage] = useState<UsagePoint[]>([])
  const [timeline, setTimeline] = useState<StringPoint[]>([])
  const [valence, setValence] = useState<SeriesPoint[]>([])
  const [arousal, setArousal] = useState<SeriesPoint[]>([])
  const [emotionHeatmap, setEmotionHeatmap] = useState<HeatmapPoint[]>([])
  const [desireMetrics, setDesireMetrics] = useState<DesireMetricSeriesMap>(
    makeEmptyDesireMetricSeriesMap,
  )

  useEffect(() => {
    if (activeTab !== 'history') return

    let disposed = false
    const bucket = bucketFor(preset)

    const loadHistory = async () => {
      const [i, u, t, v, a, emotionTimeline, heatmap, ...desireSeries] =
        await Promise.all([
          fetchIntensity(range, bucket),
          fetchUsage(range, bucket),
          fetchTimeline(range),
          fetchValence(range, bucket),
          fetchArousal(range, bucket),
          fetchStringTimeline('emotion_primary', range),
          fetchStringHeatmap('emotion_primary', range, bucket),
          ...DESIRE_METRIC_KEYS.map((key) => fetchMetric(key, range, bucket)),
        ])
      if (disposed) return
      const emotionByTimestamp = new Map(
        emotionTimeline.map((point) => [point.ts, point.value]),
      )
      setIntensity(
        i.map((point) => ({
          ...point,
          emotion_primary: emotionByTimestamp.get(point.ts),
        })),
      )
      setUsage(u)
      setTimeline(t)
      setValence(v)
      setArousal(a)
      setEmotionHeatmap(heatmap)
      setDesireMetrics({
        information_hunger: desireSeries[0] ?? [],
        social_thirst: desireSeries[1] ?? [],
        cognitive_coherence: desireSeries[2] ?? [],
        pattern_seeking: desireSeries[3] ?? [],
        predictability: desireSeries[4] ?? [],
        recognition: desireSeries[5] ?? [],
        resonance: desireSeries[6] ?? [],
        expression: desireSeries[7] ?? [],
        curiosity: desireSeries[8] ?? [],
      })
    }

    void loadHistory()
    const timer = setInterval(loadHistory, 2000)
    return () => {
      disposed = true
      clearInterval(timer)
    }
  }, [activeTab, range, preset])

  const toolSeriesKeys = useMemo(
    () =>
      Array.from(
        new Set(
          usage.flatMap((row) =>
            Object.keys(row).filter(
              (key) => key !== 'ts' && typeof row[key] === 'number',
            ),
          ),
        ),
      ).sort(),
    [usage],
  )

  const desireChartData = useMemo(() => {
    const byTs = new Map<string, Record<string, number | string>>()
    for (const key of DESIRE_METRIC_KEYS) {
      for (const point of desireMetrics[key]) {
        const row = byTs.get(point.ts) ?? { ts: point.ts }
        row[key] = point.value
        byTs.set(point.ts, row)
      }
    }
    return Array.from(byTs.values()).sort((a, b) =>
      String(a.ts).localeCompare(String(b.ts)),
    )
  }, [desireMetrics])

  return {
    intensity,
    usage,
    timeline,
    valence,
    arousal,
    emotionHeatmap,
    desireMetrics,
    toolSeriesKeys,
    desireChartData,
  }
}
