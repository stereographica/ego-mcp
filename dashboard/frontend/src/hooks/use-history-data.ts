import { useEffect, useMemo, useState } from 'react'

import {
  fetchArousal,
  fetchDesireKeys,
  fetchIntensity,
  fetchLogs,
  fetchMetric,
  fetchNotions,
  fetchStringHeatmap,
  fetchStringTimeline,
  fetchTimeline,
  fetchUsage,
  fetchValence,
} from '@/api'
import { buildDesireHistorySeriesKeys, sortDesireCatalogItems } from '@/desires'
import type {
  DateRange,
  EmotionTrendPoint,
  HeatmapPoint,
  DesireCatalogItem,
  HistoryMarker,
  IntensityPoint,
  LogPoint,
  Notion,
  SeriesPoint,
  StringPoint,
  TimeRangePreset,
  UsagePoint,
} from '@/types'

type DesireMetricSeriesMap = Record<string, SeriesPoint[]>

const makeEmptyDesireMetricSeriesMap = (
  catalog: DesireCatalogItem[],
): DesireMetricSeriesMap =>
  Object.fromEntries(
    sortDesireCatalogItems(catalog).map((item) => [item.id, []]),
  ) as Record<string, SeriesPoint[]>

const bucketFor = (preset: TimeRangePreset) =>
  preset === '15m' || preset === '1h' ? '1m' : '5m'

const rangeFor = (range: DateRange, preset: TimeRangePreset): DateRange => {
  if (preset === 'custom') {
    return range
  }
  const to = new Date()
  const from = new Date(to)
  const minutesByPreset: Record<Exclude<TimeRangePreset, 'custom'>, number> = {
    '15m': 15,
    '1h': 60,
    '6h': 360,
    '24h': 1440,
    '7d': 10080,
  }
  from.setMinutes(from.getMinutes() - minutesByPreset[preset])
  return { from: from.toISOString(), to: to.toISOString() }
}

const isNumeric = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value)

const readStringField = (log: LogPoint, key: string): string | undefined => {
  const rootValue = log[key]
  if (typeof rootValue === 'string') {
    return rootValue
  }
  const fields = log.fields
  if (fields && typeof fields[key] === 'string') {
    return fields[key] as string
  }
  return undefined
}

const readNumberField = (log: LogPoint, key: string): number | undefined => {
  const rootValue = log[key]
  if (isNumeric(rootValue)) {
    return rootValue
  }
  const fields = log.fields
  if (fields && isNumeric(fields[key])) {
    return fields[key] as number
  }
  return undefined
}

const splitCsv = (value: string | undefined) =>
  value
    ? value
        .split(',')
        .map((entry) => entry.trim())
        .filter(Boolean)
    : []

const buildMarkers = (logs: LogPoint[]): HistoryMarker[] => {
  const markers: HistoryMarker[] = []
  for (const log of logs) {
    const ts = String(log.ts ?? '')
    const proustTriggered =
      readStringField(log, 'proust_triggered') === 'true' ||
      log.fields?.proust_triggered === true
    const proustMemoryId = readStringField(log, 'proust_memory_id')
    if (proustTriggered || proustMemoryId) {
      markers.push({
        ts,
        kind: 'proust',
        label: 'Proust',
        detail: proustMemoryId ?? 'retrieval',
        memory_id: proustMemoryId,
        confidence: readNumberField(log, 'proust_memory_decay'),
      })
    }

    const impulseTriggered =
      readStringField(log, 'impulse_boost_triggered') === 'true' ||
      log.fields?.impulse_boost_triggered === true
    const boostedDesire = readStringField(log, 'impulse_boosted_desire')
    const impulseAmount = readNumberField(log, 'impulse_boost_amount')
    if (impulseTriggered && boostedDesire) {
      markers.push({
        ts,
        kind: 'impulse',
        label: 'Impulse boost',
        detail: boostedDesire,
        desire_key: boostedDesire,
        value: impulseAmount,
      })
    }

    for (const created of splitCsv(
      readStringField(log, 'emergent_desire_created'),
    )) {
      markers.push({
        ts,
        kind: 'emergent',
        label: 'Emergent desire',
        detail: created,
        desire_key: created,
      })
    }
  }
  return markers.sort((lhs, rhs) => lhs.ts.localeCompare(rhs.ts))
}

export const useHistoryData = (
  activeTab: string,
  range: DateRange,
  preset: TimeRangePreset,
  desireCatalog: DesireCatalogItem[],
) => {
  const [intensity, setIntensity] = useState<IntensityPoint[]>([])
  const [usage, setUsage] = useState<UsagePoint[]>([])
  const [timeline, setTimeline] = useState<StringPoint[]>([])
  const [valence, setValence] = useState<SeriesPoint[]>([])
  const [arousal, setArousal] = useState<SeriesPoint[]>([])
  const [emotionTrend, setEmotionTrend] = useState<EmotionTrendPoint[]>([])
  const [emotionHeatmap, setEmotionHeatmap] = useState<HeatmapPoint[]>([])
  const [historyMarkers, setHistoryMarkers] = useState<HistoryMarker[]>([])
  const [notions, setNotions] = useState<Notion[]>([])
  const [desireMetrics, setDesireMetrics] = useState<DesireMetricSeriesMap>(
    () => makeEmptyDesireMetricSeriesMap(desireCatalog),
  )
  const [desireKeys, setDesireKeys] = useState<string[]>(() =>
    buildDesireHistorySeriesKeys(desireCatalog, []),
  )

  useEffect(() => {
    if (activeTab !== 'history') return

    let disposed = false
    const bucket = bucketFor(preset)

    const loadHistory = async () => {
      const effectiveRange = rangeFor(range, preset)
      const discoveredDesireKeys = await fetchDesireKeys(effectiveRange)
      if (disposed) return

      const nextDesireKeys = buildDesireHistorySeriesKeys(
        desireCatalog,
        discoveredDesireKeys,
      )
      setDesireKeys(nextDesireKeys)

      const [i, u, t, v, a, emotionTimeline, heatmap, logs, ...desireSeries] =
        await Promise.all([
          fetchIntensity(effectiveRange, bucket),
          fetchUsage(effectiveRange, bucket),
          fetchTimeline(effectiveRange),
          fetchValence(effectiveRange, bucket),
          fetchArousal(effectiveRange, bucket),
          fetchStringTimeline('emotion_primary', effectiveRange),
          fetchStringHeatmap('emotion_primary', effectiveRange, bucket),
          fetchLogs(effectiveRange, 'ALL', ''),
          ...nextDesireKeys.map((key) =>
            fetchMetric(key, effectiveRange, bucket),
          ),
        ])
      if (disposed) return

      const emotionByTimestamp = new Map(
        emotionTimeline.map((point) => [point.ts, point.value]),
      )
      const valenceSorted = [...v].sort((lhs, rhs) =>
        lhs.ts.localeCompare(rhs.ts),
      )
      const emotionTimelineSorted = [...emotionTimeline].sort((lhs, rhs) =>
        lhs.ts.localeCompare(rhs.ts),
      )
      const nextEmotionTrend: EmotionTrendPoint[] = []
      let valenceCursor = 0
      let currentValence = 0
      for (const point of emotionTimelineSorted) {
        while (
          valenceCursor < valenceSorted.length &&
          valenceSorted[valenceCursor].ts <= point.ts
        ) {
          currentValence = Math.max(
            -1,
            Math.min(1, valenceSorted[valenceCursor].value),
          )
          valenceCursor += 1
        }
        nextEmotionTrend.push({
          ts: point.ts,
          value: currentValence,
          emotion_primary: point.value,
        })
      }

      const nextDesireMetrics = Object.fromEntries(
        nextDesireKeys.map((key, index) => [key, desireSeries[index] ?? []]),
      ) as DesireMetricSeriesMap

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
      setEmotionTrend(nextEmotionTrend)
      setEmotionHeatmap(heatmap)
      setHistoryMarkers(buildMarkers(logs))
      setDesireMetrics(nextDesireMetrics)
    }

    void loadHistory()
    const timer = setInterval(loadHistory, 2000)
    return () => {
      disposed = true
      clearInterval(timer)
    }
  }, [activeTab, desireCatalog, range, preset])

  useEffect(() => {
    if (activeTab !== 'history') return

    let disposed = false

    const loadMemorySurface = async () => {
      const notionResponse = await fetchNotions()
      if (!disposed) {
        setNotions(notionResponse.items)
      }
    }

    void loadMemorySurface()
    const timer = setInterval(loadMemorySurface, 60_000)
    return () => {
      disposed = true
      clearInterval(timer)
    }
  }, [activeTab])

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
    for (const key of desireKeys) {
      for (const point of desireMetrics[key] ?? []) {
        const row = byTs.get(point.ts) ?? { ts: point.ts }
        row[key] = point.value
        byTs.set(point.ts, row)
      }
    }
    return Array.from(byTs.values()).sort((a, b) =>
      String(a.ts).localeCompare(String(b.ts)),
    )
  }, [desireKeys, desireMetrics])

  return {
    intensity,
    usage,
    timeline,
    valence,
    arousal,
    emotionTrend,
    emotionHeatmap,
    historyMarkers,
    notions,
    desireMetrics,
    desireKeys,
    toolSeriesKeys,
    desireChartData,
  }
}
