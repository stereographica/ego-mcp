import type { HeatmapPoint } from '@/types'

export type EmotionCountRow = {
  emotion: string
  count: number
}

export const aggregateEmotionCounts = (
  heatmapData: HeatmapPoint[],
): EmotionCountRow[] => {
  const totals = new Map<string, number>()
  for (const bucket of heatmapData) {
    for (const [emotion, count] of Object.entries(bucket.counts)) {
      totals.set(emotion, (totals.get(emotion) ?? 0) + count)
    }
  }
  return Array.from(totals.entries())
    .map(([emotion, count]) => ({ emotion, count }))
    .sort((a, b) => b.count - a.count)
}
