import { AlertCircle } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useAnomalies } from '@/hooks/use-anomalies'
import { useTimestampFormatter } from '@/hooks/use-timestamp-formatter'

export const AnomalyAlerts = () => {
  const alerts = useAnomalies()
  const { formatTs } = useTimestampFormatter()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Anomaly alerts</CardTitle>
      </CardHeader>
      <CardContent>
        {alerts.length === 0 && (
          <p className="text-muted-foreground text-xs">
            No anomalies detected in the last hour.
          </p>
        )}
        <div className="space-y-2">
          {alerts.map((alert, i) => (
            <Alert key={`${alert.ts}-${i}`} variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle className="text-xs font-medium">
                {alert.kind === 'usage_spike'
                  ? 'Usage spike'
                  : 'Intensity spike'}
              </AlertTitle>
              <AlertDescription className="text-xs">
                {formatTs(alert.ts)} — value: {alert.value.toFixed(2)}
              </AlertDescription>
            </Alert>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
