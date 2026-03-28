import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { Notion } from '@/types'

type NotionPanelProps = {
  notions: Notion[]
}

const formatPercent = (value: number) => `${Math.round(value * 100)}%`

export const NotionPanel = ({ notions }: NotionPanelProps) => {
  const sorted = [...notions].sort(
    (lhs, rhs) =>
      rhs.confidence - lhs.confidence || rhs.source_count - lhs.source_count,
  )

  return (
    <Card className="min-w-0 overflow-hidden">
      <CardHeader>
        <CardTitle className="text-sm">Notions</CardTitle>
      </CardHeader>
      <CardContent className="min-w-0 space-y-3">
        <div className="flex flex-wrap gap-2 text-xs">
          <Badge variant="outline">count {sorted.length}</Badge>
          <Badge variant="outline">
            avg confidence{' '}
            {sorted.length > 0
              ? formatPercent(
                  sorted.reduce((sum, notion) => sum + notion.confidence, 0) /
                    sorted.length,
                )
              : '0%'}
          </Badge>
        </div>
        <ScrollArea className="h-[300px] min-w-0 rounded-md border">
          <div className="divide-y">
            {sorted.length === 0 ? (
              <p className="text-muted-foreground px-3 py-4 text-xs">
                No notions available.
              </p>
            ) : null}
            {sorted.map((notion) => (
              <div key={notion.id} className="space-y-2 px-3 py-3 text-xs">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{notion.label}</p>
                    <p className="text-muted-foreground truncate">
                      {notion.id}
                    </p>
                  </div>
                  <Badge variant="secondary">{notion.emotion_tone}</Badge>
                </div>
                <div className="space-y-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-muted-foreground">confidence</span>
                    <span className="font-mono tabular-nums">
                      {formatPercent(notion.confidence)}
                    </span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${Math.max(4, notion.confidence * 100)}%`,
                        backgroundColor: 'var(--color-chart-4)',
                      }}
                    />
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 text-muted-foreground">
                  <span>sources {notion.source_count}</span>
                  <span>created {notion.created.slice(0, 10) || '-'}</span>
                  <span>
                    reinforced {notion.last_reinforced.slice(0, 10) || '-'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}
