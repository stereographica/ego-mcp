import { useEffect, useMemo, useState } from 'react'

import {
  fetchArousal,
  fetchCurrent,
  fetchIntensity,
  fetchLogs,
  fetchMemoryNetwork,
  fetchMetric,
  fetchNotions,
  fetchStringHeatmap,
  fetchStringTimeline,
  fetchTimeline,
  fetchUsage,
  fetchValence,
} from '@/api'
import { DESIRE_METRIC_KEYS } from '@/constants'
import type {
  CurrentResponse,
  DateRange,
  EmotionTrendPoint,
  HeatmapPoint,
  HistoryMarker,
  IntensityPoint,
  LogPoint,
  MemoryNetworkResponse,
  Notion,
  SeriesPoint,
  StringPoint,
  TimeRangePreset,
  UsagePoint,
} from '@/types'

type DesireMetricSeriesMap = Record<string, SeriesPoint[]>

const makeEmptyDesireMetricSeriesMap = (): DesireMetricSeriesMap =>
  Object.fromEntries(DESIRE_METRIC_KEYS.map((key) => [key, []])) as Record<
    string,
    SeriesPoint[]
  >

const bucketFor = (preset: TimeRangePreset) =>
  preset === '15m' || preset === '1h' ? '1m' : '5m'

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

const discoverDesireKeys = (current: CurrentResponse | null) => {
  const fixedKeys = new Set<string>(DESIRE_METRIC_KEYS)
  const dynamicKeys = new Set<string>()
  for (const source of [
    current?.latest_desires,
    current?.latest_emergent_desires,
  ]) {
    if (!source) continue
    for (const [key, value] of Object.entries(source)) {
      if (!isNumeric(value)) continue
      if (!fixedKeys.has(key)) {
        dynamicKeys.add(key)
      }
    }
  }
  return {
    fixedKeys: [...DESIRE_METRIC_KEYS],
    dynamicKeys: [...dynamicKeys].sort(),
  }
}

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
  const [emotionTrend, setEmotionTrend] = useState<EmotionTrendPoint[]>([])
  const [emotionHeatmap, setEmotionHeatmap] = useState<HeatmapPoint[]>([])
  const [historyMarkers, setHistoryMarkers] = useState<HistoryMarker[]>([])
  const [memoryNetwork, setMemoryNetwork] = useState<MemoryNetworkResponse>({
    nodes: [],
    edges: [],
  })
  const [notions, setNotions] = useState<Notion[]>([])
  const [desireMetrics, setDesireMetrics] = useState<DesireMetricSeriesMap>(
    makeEmptyDesireMetricSeriesMap,
  )
  const [desireKeys, setDesireKeys] = useState<string[]>([
    ...DESIRE_METRIC_KEYS,
  ])

  useEffect(() => {
    if (activeTab !== 'history') return

    let disposed = false
    const bucket = bucketFor(preset)

    const loadHistory = async () => {
      const current = await fetchCurrent()
      if (disposed) return

      const { fixedKeys, dynamicKeys } = discoverDesireKeys(current)
      const nextDesireKeys = [...fixedKeys, ...dynamicKeys]
      setDesireKeys(nextDesireKeys)

      const [i, u, t, v, a, emotionTimeline, heatmap, logs, ...desireSeries] =
        await Promise.all([
          fetchIntensity(range, bucket),
          fetchUsage(range, bucket),
          fetchTimeline(range),
          fetchValence(range, bucket),
          fetchArousal(range, bucket),
          fetchStringTimeline('emotion_primary', range),
          fetchStringHeatmap('emotion_primary', range, bucket),
          fetchLogs(range, 'ALL', ''),
          ...nextDesireKeys.map((key) => fetchMetric(key, range, bucket)),
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
  }, [activeTab, range, preset])

  useEffect(() => {
    if (activeTab !== 'history') return

    let disposed = false

    const loadMemorySurface = async () => {
      const [network, notionResponse] = await Promise.all([
        fetchMemoryNetwork(),
        fetchNotions(),
      ])
      if (disposed) return

      setMemoryNetwork(network)
      setNotions(notionResponse.items)
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
    memoryNetwork,
    notions,
    desireMetrics,
    desireKeys,
    toolSeriesKeys,
    desireChartData,
  }
}
