import { StatusIndicator } from '@/components/now/status-indicator'
import type { CurrentResponse } from '@/types'

type DashboardHeaderProps = {
  current: CurrentResponse | null
  connected: boolean
}

export const DashboardHeader = ({
  current,
  connected,
}: DashboardHeaderProps) => {
  const agentName = import.meta.env.VITE_DASHBOARD_AGENT_NAME?.trim() || ''

  return (
    <header className="flex items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-bold tracking-tight">ego-mcp Dashboard</h1>
        {agentName && (
          <span
            className="bg-muted text-muted-foreground rounded px-2 py-0.5 text-xs font-medium"
            aria-label="agent name"
          >
            {agentName}
          </span>
        )}
        {!connected && (
          <span className="text-muted-foreground text-xs">(polling)</span>
        )}
      </div>
      <StatusIndicator current={current} />
    </header>
  )
}
