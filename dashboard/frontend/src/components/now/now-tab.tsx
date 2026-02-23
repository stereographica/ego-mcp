import { ActivityFeed } from '@/components/now/activity-feed'
import { AnomalyAlerts } from '@/components/now/anomaly-alerts'
import { DesireRadar } from '@/components/now/desire-radar'
import { EmotionStatus } from '@/components/now/emotion-status'
import { SessionSummary } from '@/components/now/session-summary'
import type { LogLine } from '@/hooks/use-dashboard-socket'
import type { CurrentResponse } from '@/types'

type NowTabProps = {
  current: CurrentResponse | null
  logLines: LogLine[]
}

export const NowTab = ({ current, logLines }: NowTabProps) => (
  <div className="space-y-4">
    <SessionSummary current={current} />
    <EmotionStatus current={current} />
    <div className="grid gap-4 lg:grid-cols-2">
      <DesireRadar current={current} />
      <div className="space-y-4">
        <ActivityFeed logLines={logLines} />
        <AnomalyAlerts />
      </div>
    </div>
  </div>
)
