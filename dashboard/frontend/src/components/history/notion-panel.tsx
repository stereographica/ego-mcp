import { useEffect, useMemo, useState } from 'react'

import { fetchNotionHistory } from '@/api'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { DateRange, Notion, SeriesPoint, TimeRangePreset } from '@/types'

type NotionPanelProps = {
  notions: Notion[]
  range: DateRange
  preset: TimeRangePreset
}

const formatPercent = (value: number) => `${Math.round(value * 100)}%`

const bucketFor = (preset: TimeRangePreset) => {
  switch (preset) {
    case '15m':
    case '1h':
      return '1m'
    case '6h':
    case '24h':
      return '5m'
    default:
      return '15m'
  }
}

const rangeFor = (range: DateRange, preset: TimeRangePreset): DateRange => {
  if (preset === 'custom') {
    return range
  }
  const to = new Date()
  const from = new Date(to)
  const minutesByPreset: Record<Exclude<TimeRangePreset, 'custom'>, number> = {
    '15m': 15,
    '1h': 60,
    '6h': 360,
    '24h': 1440,
    '7d': 10080,
  }
  from.setMinutes(from.getMinutes() - minutesByPreset[preset])
  return { from: from.toISOString(), to: to.toISOString() }
}

const buildSparkline = (points: SeriesPoint[], width = 320, height = 96) => {
  if (points.length === 0) {
    return ''
  }
  if (points.length === 1) {
    const y = height - points[0].value * height
    return `0,${y.toFixed(1)} ${width},${y.toFixed(1)}`
  }
  return points
    .map((point, index) => {
      const x = (index / (points.length - 1)) * width
      const y = height - point.value * height
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
}

export const NotionPanel = ({ notions, range, preset }: NotionPanelProps) => {
  const sorted = useMemo(
    () =>
      [...notions].sort(
        (lhs, rhs) =>
          rhs.confidence - lhs.confidence ||
          rhs.source_count - lhs.source_count,
      ),
    [notions],
  )
  const [selectedNotionId, setSelectedNotionId] = useState<string>('')
  const [selectedHistory, setSelectedHistory] = useState<SeriesPoint[]>([])

  useEffect(() => {
    if (sorted.length === 0) {
      setSelectedNotionId('')
      return
    }
    setSelectedNotionId((current) =>
      current && sorted.some((notion) => notion.id === current)
        ? current
        : sorted[0].id,
    )
  }, [sorted])

  useEffect(() => {
    if (!selectedNotionId) {
      setSelectedHistory([])
      return
    }
    let disposed = false
    const effectiveRange = rangeFor(range, preset)

    void fetchNotionHistory(
      selectedNotionId,
      effectiveRange,
      bucketFor(preset),
    ).then((history) => {
      if (!disposed) {
        setSelectedHistory(history)
      }
    })

    return () => {
      disposed = true
    }
  }, [preset, range, selectedNotionId])

  const selectedNotion =
    sorted.find((notion) => notion.id === selectedNotionId) ?? null
  const sparkline = buildSparkline(selectedHistory)

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
        <div className="space-y-2 rounded-md border p-3">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate text-xs font-medium">
                {selectedNotion?.label ?? 'No notion selected'}
              </p>
              <p className="text-muted-foreground text-xs">Confidence trend</p>
            </div>
            <Badge variant="outline">
              {selectedNotion ? formatPercent(selectedNotion.confidence) : '0%'}
            </Badge>
          </div>
          {sparkline ? (
            <svg
              viewBox="0 0 320 96"
              className="h-24 w-full"
              role="img"
              aria-label="Selected notion confidence trend"
            >
              <path
                d="M0 95.5 H320"
                stroke="var(--color-border)"
                strokeWidth="1"
                fill="none"
              />
              <polyline
                points={sparkline}
                fill="none"
                stroke="var(--color-chart-4)"
                strokeWidth="3"
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            </svg>
          ) : (
            <p className="text-muted-foreground text-xs">
              No confidence history in the selected range.
            </p>
          )}
        </div>
        <ScrollArea className="h-[300px] min-w-0 rounded-md border">
          <div className="divide-y">
            {sorted.length === 0 ? (
              <p className="text-muted-foreground px-3 py-4 text-xs">
                No notions available.
              </p>
            ) : null}
            {sorted.map((notion) => (
              <button
                key={notion.id}
                type="button"
                className="block w-full space-y-2 px-3 py-3 text-left text-xs"
                onClick={() => setSelectedNotionId(notion.id)}
              >
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
              </button>
            ))}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}
