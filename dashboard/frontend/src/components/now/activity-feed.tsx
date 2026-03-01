import { useEffect, useRef } from 'react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { LogLine } from '@/types'
import { useTimestampFormatter } from '@/hooks/use-timestamp-formatter'

type ActivityFeedProps = {
  logLines: LogLine[]
  connected: boolean
}

export const ActivityFeed = ({ logLines, connected }: ActivityFeedProps) => {
  const { formatTs } = useTimestampFormatter()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const element = bottomRef.current
    if (!element) return
    const viewport = element.closest('[data-radix-scroll-area-viewport]')
    if (viewport instanceof HTMLElement) {
      viewport.scrollTop = viewport.scrollHeight
    }
  }, [logLines])

  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-sm">Activity feed</CardTitle>
        <Badge
          variant={connected ? 'secondary' : 'outline'}
          className="text-[10px]"
        >
          {connected ? 'WebSocket' : 'HTTP polling'}
        </Badge>
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
                className="flex min-w-0 flex-wrap items-start gap-x-2 gap-y-1 text-xs"
              >
                <span className="text-muted-foreground shrink-0 font-mono">
                  {formatTs(item.ts)}
                </span>
                {item.tool_name && (
                  <Badge
                    variant="outline"
                    className="max-w-[8rem] truncate text-[10px]"
                  >
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
                  <Badge
                    variant="outline"
                    className="max-w-[8rem] truncate text-[10px]"
                  >
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
