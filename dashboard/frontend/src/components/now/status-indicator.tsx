import { Badge } from '@/components/ui/badge'
import type { CurrentResponse } from '@/types'

type StatusIndicatorProps = {
  current: CurrentResponse | null
}

type StatusLevel = 'active' | 'idle' | 'no_data'

const getStatus = (current: CurrentResponse | null): StatusLevel => {
  const ts = current?.latest?.ts
  if (!ts) return 'no_data'
  const age = Date.now() - new Date(ts).getTime()
  if (age <= 15 * 60_000) return 'active'
  if (age <= 60 * 60_000) return 'idle'
  return 'no_data'
}

const STATUS_CONFIG: Record<
  StatusLevel,
  { label: string; variant: 'default' | 'secondary' | 'destructive' }
> = {
  active: { label: 'Active', variant: 'default' },
  idle: { label: 'Idle', variant: 'secondary' },
  no_data: { label: 'No recent activity', variant: 'secondary' },
}

export const StatusIndicator = ({ current }: StatusIndicatorProps) => {
  const status = getStatus(current)
  const config = STATUS_CONFIG[status]

  return (
    <Badge variant={config.variant} className="gap-1.5">
      <span
        className={`inline-block h-2 w-2 rounded-full ${
          status === 'active'
            ? 'animate-pulse bg-green-400'
            : status === 'idle'
              ? 'bg-yellow-400'
              : 'bg-muted-foreground'
        }`}
      />
      {config.label}
    </Badge>
  )
}
