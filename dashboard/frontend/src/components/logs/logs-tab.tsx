import { useEffect, useRef, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useLogData } from '@/hooks/use-log-data'
import { useTimestampFormatter } from '@/hooks/use-timestamp-formatter'
import type { DateRange } from '@/types'

type LogsTabProps = {
  range: DateRange
  isActive: boolean
}

const LOG_LEVELS = ['ALL', 'INFO', 'WARNING', 'ERROR'] as const

const levelVariant = (
  level: string,
): 'default' | 'secondary' | 'destructive' | 'outline' => {
  switch (level) {
    case 'ERROR':
      return 'destructive'
    case 'WARNING':
      return 'outline'
    case 'INFO':
      return 'secondary'
    default:
      return 'default'
  }
}

const isNearBottom = (el: HTMLElement, threshold = 24) =>
  el.scrollHeight - el.scrollTop - el.clientHeight <= threshold

export const LogsTab = ({ range, isActive }: LogsTabProps) => {
  const [logLevel, setLogLevel] = useState('ALL')
  const [loggerFilter, setLoggerFilter] = useState('')
  const [autoScroll, setAutoScroll] = useState(true)
  const [logFeedPinned, setLogFeedPinned] = useState(true)
  const logViewportRef = useRef<HTMLDivElement | null>(null)
  const { formatTs, clientTimeZone } = useTimestampFormatter()

  const logs = useLogData(isActive, range, logLevel, loggerFilter)

  useEffect(() => {
    if (!isActive || !autoScroll || !logFeedPinned) return
    const el = logViewportRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [isActive, logs, autoScroll, logFeedPinned])

  useEffect(() => {
    if (!isActive) return
    setLogFeedPinned(true)
    requestAnimationFrame(() => {
      const el = logViewportRef.current
      if (!el) return
      el.scrollTop = el.scrollHeight
    })
  }, [isActive])

  return (
    <Card className="min-h-[clamp(380px,62vh,820px)]">
      <CardHeader>
        <CardTitle className="text-sm">Live tail</CardTitle>
        <p className="text-muted-foreground text-xs">
          Timestamps: {clientTimeZone}
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Select value={logLevel} onValueChange={setLogLevel}>
            <SelectTrigger className="w-[120px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LOG_LEVELS.map((level) => (
                <SelectItem key={level} value={level}>
                  {level}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <input
            className="rounded-md border border-input bg-secondary px-2 py-1 text-sm"
            placeholder="logger"
            value={loggerFilter}
            onChange={(e) => setLoggerFilter(e.target.value)}
          />
          <label className="flex items-center gap-1.5 text-xs">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
            />
            auto scroll
          </label>
        </div>

        <ScrollArea
          className="h-[clamp(360px,62vh,820px)]"
          viewportRef={logViewportRef}
          onViewportScroll={(e) =>
            setLogFeedPinned(isNearBottom(e.currentTarget))
          }
        >
          <div className="space-y-2">
            {logs.map((item, index) => {
              const { ts, level, ...rest } = item
              return (
                <div
                  key={`log-${ts}-${String(item.logger)}-${index}`}
                  className="grid grid-cols-[196px_minmax(0,1fr)] items-start gap-3 rounded-md bg-secondary/50 p-2"
                >
                  <div
                    className="flex items-center gap-1.5 font-mono text-xs text-muted-foreground"
                    title={ts}
                  >
                    <Badge
                      variant={levelVariant(level)}
                      className="text-[10px]"
                    >
                      {level}
                    </Badge>
                    {formatTs(ts)}
                  </div>
                  <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed">
                    {JSON.stringify(rest, null, 2)}
                  </pre>
                </div>
              )
            })}
            {logs.length === 0 && (
              <p className="text-muted-foreground text-xs">
                No log lines in selected range.
              </p>
            )}
          </div>
        </ScrollArea>

        {autoScroll && !logFeedPinned && (
          <p className="text-muted-foreground text-xs">
            Auto scroll is enabled, but paused because you scrolled away from
            the bottom.
          </p>
        )}
      </CardContent>
    </Card>
  )
}
