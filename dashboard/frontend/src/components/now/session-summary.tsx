import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { CurrentResponse } from '@/types'

type SessionSummaryProps = {
  current: CurrentResponse | null
}

export const SessionSummary = ({ current }: SessionSummaryProps) => (
  <div className="grid gap-4 sm:grid-cols-3">
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-muted-foreground text-xs font-medium">
          tool calls (24h total)
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-bold">
          {current?.window_24h?.tool_calls ?? 0}
        </p>
      </CardContent>
    </Card>

    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-muted-foreground text-xs font-medium">
          error rate (24h)
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-bold">
          {(((current?.window_24h?.error_rate ?? 0) as number) * 100).toFixed(
            1,
          )}
          %
        </p>
      </CardContent>
    </Card>

    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-muted-foreground text-xs font-medium">
          latest latency
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-bold">
          {current?.latest?.duration_ms != null
            ? `${current.latest.duration_ms}ms`
            : 'n/a'}
        </p>
      </CardContent>
    </Card>
  </div>
)
