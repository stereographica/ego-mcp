import { useEffect, useMemo, useState } from 'react'

import { fetchNotionHistory } from '@/api'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { notionToneGroup } from '@/components/memory/memory-graph-palette'
import type { MemoryNetworkNode, MetaField, SeriesPoint } from '@/types'

type NotionDetailPanelProps = {
  notion: MemoryNetworkNode
  relatedNotionIds: string[]
  sourceMemoryIds: string[]
  onNotionClick?: (notionId: string) => void
}

const MetaFieldDisplay = ({
  fieldKey,
  field,
  onNotionClick,
}: {
  fieldKey: string
  field: MetaField
  onNotionClick?: (notionId: string) => void
}) => {
  if (field.type === 'text') {
    return (
      <div className="rounded-md border bg-muted/10 px-3 py-2">
        <span className="text-muted-foreground font-medium">{fieldKey}:</span>
        <span className="ml-2">{field.value}</span>
      </div>
    )
  }

  if (field.type === 'file_path') {
    return (
      <div className="rounded-md border bg-muted/10 px-3 py-2">
        <span className="text-muted-foreground font-medium">{fieldKey}:</span>
        <span className="ml-2 font-mono text-xs">{field.path}</span>
      </div>
    )
  }

  if (field.type === 'notion_ids') {
    return (
      <div className="rounded-md border bg-muted/10 px-3 py-2">
        <span className="text-muted-foreground font-medium">{fieldKey}:</span>
        <div className="mt-1 flex flex-wrap gap-1">
          {field.notion_ids.map((id) => (
            <button
              key={id}
              onClick={() => onNotionClick?.(id)}
              className="rounded bg-amber-500/20 px-2 py-0.5 text-xs text-amber-300 hover:bg-amber-500/30 transition-colors cursor-pointer"
            >
              {id}
            </button>
          ))}
        </div>
      </div>
    )
  }

  return null
}

const formatTimestamp = (value?: string | null) =>
  value ? new Date(value).toLocaleString() : 'n/a'

const buildSparkline = (points: SeriesPoint[], width = 220, height = 56) => {
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

export const NotionDetailPanel = ({
  notion,
  relatedNotionIds,
  sourceMemoryIds,
  onNotionClick,
}: NotionDetailPanelProps) => {
  const [history, setHistory] = useState<SeriesPoint[]>([])

  useEffect(() => {
    let disposed = false
    const to = new Date()
    const from = new Date(to)
    from.setDate(from.getDate() - 7)

    void fetchNotionHistory(
      notion.id,
      { from: from.toISOString(), to: to.toISOString() },
      '15m',
    ).then((items) => {
      if (!disposed) {
        setHistory(items)
      }
    })

    return () => {
      disposed = true
    }
  }, [notion.id])

  const toneGroup = notionToneGroup(notion.emotion_tone)
  const sparkline = useMemo(() => buildSparkline(history), [history])

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="text-sm">Notion detail</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5 text-sm">
        <div className="space-y-1">
          <p className="font-medium">{notion.label ?? notion.id}</p>
          <p className="text-muted-foreground text-xs">
            {`${formatTimestamp(notion.created)} -> ${formatTimestamp(
              notion.last_reinforced,
            )}`}
          </p>
        </div>

        <div className="space-y-2 rounded-lg border bg-muted/10 p-3">
          <div className="flex items-center justify-between gap-3">
            <span className="text-muted-foreground text-xs uppercase tracking-wide">
              Confidence
            </span>
            <span className="font-semibold">
              {(notion.confidence ?? 0).toFixed(2)}
            </span>
          </div>
          <div className="h-2 rounded-full bg-muted/40">
            <div
              className="h-2 rounded-full bg-amber-400"
              style={{
                width: `${Math.max(0, Math.min(100, (notion.confidence ?? 0) * 100))}%`,
              }}
            />
          </div>
          <div className="rounded-md border bg-slate-950/70 p-2">
            {sparkline ? (
              <svg viewBox="0 0 220 56" className="h-14 w-full">
                <polyline
                  points={sparkline}
                  fill="none"
                  stroke="rgb(250 204 21)"
                  strokeWidth="2.5"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
              </svg>
            ) : (
              <p className="text-muted-foreground text-xs">
                No confidence history available yet.
              </p>
            )}
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Badge variant="outline">
            {`Reinforced ${notion.reinforcement_count ?? 0}`}
          </Badge>
          <Badge variant="outline">{`Sources ${notion.source_count ?? 0}`}</Badge>
          <Badge variant="outline">{`Emotion ${notion.emotion_tone ?? 'neutral'}`}</Badge>
          <Badge variant="outline">{toneGroup}</Badge>
          {notion.is_conviction ? (
            <Badge variant="secondary">conviction</Badge>
          ) : null}
          {notion.person_id ? (
            <Badge variant="outline">{notion.person_id}</Badge>
          ) : null}
          {(notion.tags ?? []).map((tag) => (
            <Badge key={tag} variant="secondary">
              #{tag}
            </Badge>
          ))}
        </div>

        {(() => {
          const metaFields = notion.meta_fields ?? {}
          const metaFieldEntries = Object.entries(metaFields)
          if (metaFieldEntries.length === 0) {
            return null
          }
          return (
            <div className="space-y-2">
              <p className="text-muted-foreground text-xs uppercase tracking-wide">
                Meta fields ({metaFieldEntries.length})
              </p>
              <div className="space-y-2 text-xs">
                {metaFieldEntries.map(([key, field]) => (
                  <MetaFieldDisplay
                    key={key}
                    fieldKey={key}
                    field={field}
                    onNotionClick={onNotionClick}
                  />
                ))}
              </div>
            </div>
          )
        })()}

        <div className="space-y-2">
          <p className="text-muted-foreground text-xs uppercase tracking-wide">
            Source memories ({sourceMemoryIds.length})
          </p>
          <div className="space-y-2 text-xs">
            {sourceMemoryIds.length > 0 ? (
              sourceMemoryIds.map((id) => (
                <div
                  key={id}
                  className="rounded-md border bg-muted/10 px-3 py-2"
                >
                  {`○ ${id}`}
                </div>
              ))
            ) : (
              <p>No source memories.</p>
            )}
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-muted-foreground text-xs uppercase tracking-wide">
            Related notions ({relatedNotionIds.length})
          </p>
          <div className="space-y-2 text-xs">
            {relatedNotionIds.length > 0 ? (
              relatedNotionIds.map((id) => (
                <div
                  key={id}
                  className="rounded-md border bg-muted/10 px-3 py-2"
                >
                  {`⬡ ${id}`}
                </div>
              ))
            ) : (
              <p>No related notions.</p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
