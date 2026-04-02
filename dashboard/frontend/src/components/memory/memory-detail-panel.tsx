import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { MemoryDetail } from '@/types'

type MemoryDetailPanelProps = {
  detail: MemoryDetail
}

const formatTimestamp = (value: string) =>
  value ? new Date(value).toLocaleString() : 'n/a'

export const MemoryDetailPanel = ({ detail }: MemoryDetailPanelProps) => (
  <Card className="h-full">
    <CardHeader>
      <CardTitle className="text-sm">Memory detail</CardTitle>
    </CardHeader>
    <CardContent className="space-y-4 text-sm">
      <div className="space-y-1">
        <p className="font-medium">{detail.category}</p>
        <p className="text-muted-foreground text-xs">
          {formatTimestamp(detail.timestamp)}
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <Badge variant="outline">{`importance ${detail.importance}`}</Badge>
        <Badge variant="outline">{`decay ${detail.decay.toFixed(2)}`}</Badge>
        <Badge variant="outline">{`access ${detail.access_count}`}</Badge>
        {detail.is_private ? <Badge variant="secondary">private</Badge> : null}
      </div>

      <div className="space-y-2">
        <p className="text-muted-foreground text-xs uppercase tracking-wide">
          Content
        </p>
        <div className="rounded-md border bg-muted/20 p-3 whitespace-pre-wrap">
          {detail.content}
        </div>
      </div>

      <div className="space-y-2">
        <p className="text-muted-foreground text-xs uppercase tracking-wide">
          Emotional trace
        </p>
        <div className="grid gap-2 text-xs">
          <p>{`Valence ${detail.emotional_trace.valence.toFixed(2)}`}</p>
          <p>{`Arousal ${detail.emotional_trace.arousal.toFixed(2)}`}</p>
          <p>{`Intensity ${detail.emotional_trace.intensity.toFixed(2)}`}</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {(detail.tags ?? []).map((tag) => (
          <Badge key={tag} variant="secondary">
            #{tag}
          </Badge>
        ))}
      </div>

      <div className="space-y-2">
        <p className="text-muted-foreground text-xs uppercase tracking-wide">
          Linked memories
        </p>
        <div className="space-y-1 text-xs">
          {detail.linked_ids.length > 0 ? (
            detail.linked_ids.map((link) => (
              <p key={`${link.target_id}-${link.link_type}`}>
                <span>{link.target_id}</span> <span>{link.link_type}</span>{' '}
                <span>{link.confidence.toFixed(2)}</span>
              </p>
            ))
          ) : (
            <p>No linked memories.</p>
          )}
        </div>
      </div>

      <div className="space-y-2">
        <p className="text-muted-foreground text-xs uppercase tracking-wide">
          Generated notions
        </p>
        <div className="space-y-1 text-xs">
          {detail.generated_notion_ids.length > 0 ? (
            detail.generated_notion_ids.map((id) => <p key={id}>{id}</p>)
          ) : (
            <p>No generated notions.</p>
          )}
        </div>
      </div>
    </CardContent>
  </Card>
)
