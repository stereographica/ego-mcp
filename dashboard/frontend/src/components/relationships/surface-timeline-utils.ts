import type { PersonOverview, SurfaceTimelinePoint } from '@/types'

const RESONANT_COLOR = '#3b82f6'
const INVOLUNTARY_COLOR = '#f59e0b'

export type SurfaceTimelineChartPoint = {
  ts: number
  tsLabel: string
  person_id: string
  display_name: string
  surface_type: SurfaceTimelinePoint['surface_type']
  fill: string
}

export const buildPersonNameMap = (persons: PersonOverview[]) => {
  const map = new Map<string, string>()
  for (const person of persons) {
    map.set(person.person_id, person.name || person.person_id)
  }
  return map
}

export const formatSurfaceType = (
  surfaceType: SurfaceTimelinePoint['surface_type'],
) => (surfaceType === 'resonant' ? 'Resonant' : 'Involuntary')

export const buildSurfaceTimelineData = (
  points: SurfaceTimelinePoint[],
  personNameMap: Map<string, string>,
): SurfaceTimelineChartPoint[] =>
  [...points]
    .sort((a, b) => a.ts.localeCompare(b.ts))
    .map((point) => ({
      ts: new Date(point.ts).getTime(),
      tsLabel: point.ts,
      person_id: point.person_id,
      display_name: personNameMap.get(point.person_id) || point.person_id,
      surface_type: point.surface_type,
      fill:
        point.surface_type === 'resonant' ? RESONANT_COLOR : INVOLUNTARY_COLOR,
    }))
