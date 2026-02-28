import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { CurrentResponse } from '@/types'

type EmotionStatusProps = {
  current: CurrentResponse | null
}

const relativeAge = (timestamp: string): string | null => {
  const parsed = new Date(timestamp)
  if (Number.isNaN(parsed.getTime())) return null
  const seconds = Math.max(
    0,
    Math.floor((Date.now() - parsed.getTime()) / 1000),
  )
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.max(1, Math.floor(seconds / 60))}m ago`
  if (seconds < 86400) return `${Math.max(1, Math.floor(seconds / 3600))}h ago`
  return `${Math.max(1, Math.floor(seconds / 86400))}d ago`
}

export const EmotionStatus = ({ current }: EmotionStatusProps) => {
  const emotionData = current?.latest_emotion ?? current?.latest
  const intensity = emotionData?.emotion_intensity ?? 0
  const emotion = emotionData?.emotion_primary ?? 'n/a'
  const valence =
    current?.latest_emotion?.valence ??
    current?.latest?.numeric_metrics?.valence
  const arousal =
    current?.latest_emotion?.arousal ??
    current?.latest?.numeric_metrics?.arousal
  const age = emotionData?.ts ? relativeAge(emotionData.ts) : null

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-sm">Emotional state</CardTitle>
        {age && <span className="text-muted-foreground text-xs">{age}</span>}
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
