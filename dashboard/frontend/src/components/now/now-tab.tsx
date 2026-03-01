import { ActivityFeed } from '@/components/now/activity-feed'
import { AnomalyAlerts } from '@/components/now/anomaly-alerts'
import { CircumplexCard } from '@/components/now/circumplex-card'
import { DesireRadar } from '@/components/now/desire-radar'
import { EmotionStatus } from '@/components/now/emotion-status'
import { RelationshipStatus } from '@/components/now/relationship-status'
import { SessionSummary } from '@/components/now/session-summary'
import type { CurrentResponse, LogLine } from '@/types'

type NowTabProps = {
  current: CurrentResponse | null
  logLines: LogLine[]
  connected: boolean
}

export const NowTab = ({ current, logLines, connected }: NowTabProps) => (
  <div className="space-y-4">
    <SessionSummary />
    <div className="grid gap-4 lg:grid-cols-2">
      <EmotionStatus current={current} />
      <RelationshipStatus current={current} />
    </div>
    <div className="grid gap-4 lg:grid-cols-2">
      <DesireRadar current={current} />
      <CircumplexCard current={current} />
    </div>
    <div className="grid gap-4 lg:grid-cols-2">
      <ActivityFeed logLines={logLines} connected={connected} />
      <AnomalyAlerts />
    </div>
  </div>
)
