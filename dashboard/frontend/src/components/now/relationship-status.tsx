import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { CurrentResponse } from '@/types'

type RelationshipStatusProps = {
  current: CurrentResponse | null
}

const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value))

export const RelationshipStatus = ({ current }: RelationshipStatusProps) => {
  const relationship = current?.latest_relationship
  const trustLevel = relationship?.trust_level ?? 0
  const totalInteractions = Math.max(
    0,
    Math.round(relationship?.total_interactions ?? 0),
  )
  const sharedEpisodesCount = Math.max(
    0,
    Math.round(relationship?.shared_episodes_count ?? 0),
  )
  const trustPercent = clamp(trustLevel, 0, 1) * 100

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Relationship status</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <p className="text-muted-foreground mb-1 text-xs">trust</p>
          <div className="flex items-center gap-2">
            <div className="bg-secondary h-2 flex-1 overflow-hidden rounded-full">
              <div
                className="bg-chart-2 h-full rounded-full transition-all"
                style={{ width: `${trustPercent}%` }}
              />
            </div>
            <span className="text-xs tabular-nums">
              {trustLevel.toFixed(2)}
            </span>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-muted-foreground mb-1 text-xs">interactions</p>
            <p className="text-lg font-semibold tabular-nums">
              {totalInteractions}
            </p>
          </div>
          <div>
            <p className="text-muted-foreground mb-1 text-xs">
              shared episodes
            </p>
            <p className="text-lg font-semibold tabular-nums">
              {sharedEpisodesCount}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
