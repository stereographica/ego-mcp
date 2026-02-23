import type { ChartConfig } from '@/components/ui/chart'

export const DESIRE_METRIC_KEYS = [
  'information_hunger',
  'social_thirst',
  'cognitive_coherence',
  'pattern_seeking',
  'predictability',
  'recognition',
  'resonance',
  'expression',
  'curiosity',
] as const

export type DesireMetricKey = (typeof DESIRE_METRIC_KEYS)[number]

export const formatMetricLabel = (key: string) => key.replaceAll('_', ' ')

export const DESIRE_CHART_CONFIG: ChartConfig = {
  information_hunger: {
    label: 'information hunger',
    color: 'var(--color-chart-1)',
  },
  social_thirst: { label: 'social thirst', color: 'var(--color-chart-2)' },
  cognitive_coherence: {
    label: 'cognitive coherence',
    color: 'var(--color-chart-3)',
  },
  pattern_seeking: { label: 'pattern seeking', color: 'var(--color-chart-4)' },
  predictability: { label: 'predictability', color: 'var(--color-chart-5)' },
  recognition: { label: 'recognition', color: 'var(--color-chart-6)' },
  resonance: { label: 'resonance', color: 'var(--color-chart-7)' },
  expression: { label: 'expression', color: 'var(--color-chart-8)' },
  curiosity: { label: 'curiosity', color: 'var(--color-chart-9)' },
} satisfies ChartConfig

export const TOOL_CHART_COLORS = [
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
