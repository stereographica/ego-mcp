import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { CurrentResponse } from '@/types'

type EmotionStatusProps = {
  current: CurrentResponse | null
}

export const EmotionStatus = ({ current }: EmotionStatusProps) => {
  const latest = current?.latest
  const intensity = latest?.emotion_intensity ?? 0
  const emotion = latest?.emotion_primary ?? 'n/a'
  const valence = latest?.numeric_metrics?.valence
  const arousal = latest?.numeric_metrics?.arousal

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Emotional state</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div>
            <p className="text-muted-foreground mb-1 text-xs">emotion</p>
            <Badge variant="secondary" className="text-sm">
              {emotion}
            </Badge>
          </div>
          <div>
            <p className="text-muted-foreground mb-1 text-xs">intensity</p>
            <div className="flex items-center gap-2">
              <div className="bg-secondary h-2 flex-1 overflow-hidden rounded-full">
                <div
                  className="bg-primary h-full rounded-full transition-all"
                  style={{ width: `${intensity * 100}%` }}
                />
              </div>
              <span className="text-xs tabular-nums">
                {intensity.toFixed(2)}
              </span>
            </div>
          </div>
          <div>
            <p className="text-muted-foreground mb-1 text-xs">valence</p>
            <span className="text-sm font-medium tabular-nums">
              {valence != null ? valence.toFixed(2) : 'n/a'}
            </span>
          </div>
          <div>
            <p className="text-muted-foreground mb-1 text-xs">arousal</p>
            <span className="text-sm font-medium tabular-nums">
              {arousal != null ? arousal.toFixed(2) : 'n/a'}
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
