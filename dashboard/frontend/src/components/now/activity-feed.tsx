import { useEffect, useRef } from 'react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { LogLine } from '@/hooks/use-dashboard-socket'
import { useTimestampFormatter } from '@/hooks/use-timestamp-formatter'

type ActivityFeedProps = {
  logLines: LogLine[]
}

export const ActivityFeed = ({ logLines }: ActivityFeedProps) => {
  const { formatTs } = useTimestampFormatter()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logLines])

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Activity feed</CardTitle>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[220px]">
          {logLines.length === 0 && (
            <p className="text-muted-foreground text-xs">
              Waiting for activity...
            </p>
          )}
          <div className="space-y-2">
            {logLines.map((item, i) => (
              <div
                key={`${item.ts}-${i}`}
                className="flex items-start gap-2 text-xs"
              >
                <span className="text-muted-foreground shrink-0 font-mono">
                  {formatTs(item.ts)}
                </span>
                {item.tool_name && (
                  <Badge variant="outline" className="text-[10px]">
                    {item.tool_name}
                  </Badge>
                )}
                <Badge
                  variant={item.ok ? 'secondary' : 'destructive'}
                  className="text-[10px]"
                >
                  {item.ok ? 'ok' : 'error'}
                </Badge>
                {item.level && !item.tool_name && (
                  <Badge variant="outline" className="text-[10px]">
                    {item.level}
                  </Badge>
                )}
                <div className="min-w-0 flex-1">
                  {item.message && (
                    <p className="truncate text-xs leading-4">{item.message}</p>
                  )}
                  {item.logger && (
                    <p className="text-muted-foreground truncate text-[10px] leading-4">
                      {item.logger}
                    </p>
                  )}
                </div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}
