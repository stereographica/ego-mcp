import { StatusIndicator } from '@/components/now/status-indicator'
import type { CurrentResponse } from '@/types'

type DashboardHeaderProps = {
  current: CurrentResponse | null
  connected: boolean
}

export const DashboardHeader = ({
  current,
  connected,
}: DashboardHeaderProps) => (
  <header className="flex items-center justify-between gap-4">
    <div className="flex items-center gap-3">
      <h1 className="text-xl font-bold tracking-tight">ego-mcp Dashboard</h1>
      {!connected && (
        <span className="text-muted-foreground text-xs">(polling)</span>
      )}
    </div>
    <StatusIndicator current={current} />
  </header>
)
