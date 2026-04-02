import type { ChartConfig } from '@/components/ui/chart'
import type { CurrentResponse, DesireCatalogItem } from '@/types'

const LEGACY_FIXED_DESIRE_IDS = new Set([
  'information_hunger',
  'social_thirst',
  'cognitive_coherence',
  'pattern_seeking',
  'predictability',
  'recognition',
  'resonance',
  'expression',
  'curiosity',
])

const DESIRE_SERIES_COLORS = [
  'var(--color-chart-1)',
  'var(--color-chart-2)',
  'var(--color-chart-3)',
  'var(--color-chart-4)',
  'var(--color-chart-5)',
  'var(--color-chart-6)',
  'var(--color-chart-7)',
  'var(--color-chart-8)',
  'var(--color-chart-9)',
]

const DYNAMIC_DESIRE_COLORS = [
  'var(--color-chart-4)',
  'var(--color-chart-5)',
  'var(--color-chart-6)',
  'var(--color-chart-7)',
  'var(--color-chart-8)',
  'var(--color-chart-9)',
]

export const formatDesireLabel = (key: string) => key.replaceAll('_', ' ')

export const sortDesireCatalogItems = (items: DesireCatalogItem[]) =>
  [...items].sort(
    (lhs, rhs) =>
      lhs.maslow_level - rhs.maslow_level || lhs.id.localeCompare(rhs.id),
  )

const catalogKeySet = (items: DesireCatalogItem[]) =>
  new Set(items.map((item) => item.id))

const buildFixedChartConfig = (items: DesireCatalogItem[]): ChartConfig => {
  const sorted = sortDesireCatalogItems(items)
  return Object.fromEntries(
    sorted.map((item, index) => [
      item.id,
      {
        label: item.display_name,
        color: DESIRE_SERIES_COLORS[index % DESIRE_SERIES_COLORS.length],
      },
    ]),
  ) as ChartConfig
}

const buildDynamicChartConfig = (dynamicKeys: string[]): ChartConfig =>
  Object.fromEntries(
    dynamicKeys.map((key, index) => [
      key,
      {
        label: formatDesireLabel(key),
        color: DYNAMIC_DESIRE_COLORS[index % DYNAMIC_DESIRE_COLORS.length],
      },
    ]),
  ) as ChartConfig

export const buildDesireHistorySeriesKeys = (
  catalog: DesireCatalogItem[],
  discoveredKeys: string[],
) => {
  const fixedKeys = sortDesireCatalogItems(catalog).map((item) => item.id)
  const discoveredSet = new Set(discoveredKeys)
  const catalogIds = catalogKeySet(catalog)
  const dynamicKeys = [...discoveredSet]
    .filter(
      (key) =>
        !catalogIds.has(key) &&
        (catalog.length === 0 || !LEGACY_FIXED_DESIRE_IDS.has(key)) &&
        key.trim().length > 0,
    )
    .sort((lhs, rhs) => lhs.localeCompare(rhs))

  return [...fixedKeys, ...dynamicKeys]
}

export const buildDesireHistoryChartConfig = (
  catalog: DesireCatalogItem[],
  seriesKeys: string[],
): ChartConfig => {
  const fixedChartConfig = buildFixedChartConfig(catalog)
  const catalogIds = catalogKeySet(catalog)
  const dynamicKeys = seriesKeys.filter(
    (key) => !catalogIds.has(key) && !LEGACY_FIXED_DESIRE_IDS.has(key),
  )
  return {
    ...fixedChartConfig,
    ...buildDynamicChartConfig(dynamicKeys),
  }
}

export const buildDesireRadarSeriesData = (
  catalog: DesireCatalogItem[],
  current: Pick<
    CurrentResponse,
    'latest_desires' | 'latest_emergent_desires' | 'latest'
  > | null,
) => {
  const sortedCatalog = sortDesireCatalogItems(catalog)
  const catalogIds = catalogKeySet(sortedCatalog)
  const fixedDesires = current?.latest_desires ?? {}
  const emergentDesires = current?.latest_emergent_desires ?? {}
  const fallbackFixedKeys =
    sortedCatalog.length === 0
      ? Object.keys(fixedDesires)
          .filter((key) => key.trim().length > 0)
          .sort((lhs, rhs) => lhs.localeCompare(rhs))
      : []
  const dynamicKeys = Object.keys(emergentDesires)
    .filter(
      (key) =>
        !catalogIds.has(key) &&
        !fallbackFixedKeys.includes(key) &&
        (sortedCatalog.length === 0 || !LEGACY_FIXED_DESIRE_IDS.has(key)) &&
        key.trim().length > 0,
    )
    .sort((lhs, rhs) => lhs.localeCompare(rhs))
  const axisKeys = [
    ...(sortedCatalog.length > 0
      ? sortedCatalog.map((item) => item.id)
      : fallbackFixedKeys),
    ...dynamicKeys,
  ]

  const chartData = axisKeys.map((key) => {
    const catalogItem = sortedCatalog.find((item) => item.id === key)
    const value = fixedDesires[key] ?? emergentDesires[key] ?? 0
    return {
      key,
      name: catalogItem?.display_name ?? formatDesireLabel(key),
      fixed_desires: catalogItem || fallbackFixedKeys.includes(key) ? value : 0,
      dynamic_desires:
        catalogItem || fallbackFixedKeys.includes(key) ? 0 : value,
      boosted_desire: 0,
    }
  })

  const boostedDesire =
    current?.latest?.string_metrics?.impulse_boosted_desire ?? undefined
  const boostAmount = current?.latest?.numeric_metrics?.impulse_boost_amount
  const chartConfig: ChartConfig = {
    fixed_desires: {
      label: 'fixed desires',
      color: 'var(--color-chart-2)',
    },
    dynamic_desires: {
      label: 'dynamic desires',
      color: 'var(--color-chart-4)',
    },
    boosted_desire: {
      label: 'impulse boost',
      color: 'var(--color-chart-1)',
    },
  }

  return {
    chartConfig,
    chartData: chartData.map((item) => ({
      ...item,
      boosted_desire:
        item.key === boostedDesire
          ? item.fixed_desires || item.dynamic_desires
          : 0,
    })),
    hasDynamicDesires: dynamicKeys.length > 0,
    boostedDesire,
    boostAmount,
  }
}
