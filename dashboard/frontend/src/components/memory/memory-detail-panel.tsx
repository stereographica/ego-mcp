import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { MemoryDetail } from '@/types'

type MemoryDetailPanelProps = {
  detail: MemoryDetail
}

const formatTimestamp = (value: string) =>
  value ? new Date(value).toLocaleString() : 'n/a'

const MetricBar = ({
  label,
  value,
  normalized,
}: {
  label: string
  value: string
  normalized: number
}) => (
  <div className="space-y-1">
    <div className="flex items-center justify-between text-xs">
      <span className="text-muted-foreground uppercase tracking-wide">
        {label}
      </span>
      <span>{value}</span>
    </div>
    <div className="h-2 rounded-full bg-muted/40">
      <div
        className="h-2 rounded-full bg-emerald-400"
        style={{ width: `${Math.max(0, Math.min(100, normalized * 100))}%` }}
      />
    </div>
  </div>
)

const ImportanceDots = ({ importance }: { importance: number }) => (
  <div className="flex gap-1">
    {Array.from({ length: 5 }, (_, index) => (
      <span
        key={index}
        className={`h-2.5 w-2.5 rounded-full ${
          index < importance ? 'bg-amber-400' : 'bg-muted'
        }`}
      />
    ))}
  </div>
)

export const MemoryDetailPanel = ({ detail }: MemoryDetailPanelProps) => (
  <Card className="h-full">
    <CardHeader>
      <CardTitle className="text-sm">Memory detail</CardTitle>
    </CardHeader>
    <CardContent className="space-y-5 text-sm">
      <div className="space-y-1">
        <div className="flex items-center justify-between gap-3">
          <p className="font-medium">{detail.category}</p>
          <ImportanceDots importance={detail.importance} />
        </div>
        <p className="text-muted-foreground text-xs">
          {formatTimestamp(detail.timestamp)}
        </p>
      </div>

      <div className="grid gap-3 rounded-lg border bg-muted/10 p-3">
        <MetricBar
          label="Decay"
          value={detail.decay.toFixed(2)}
          normalized={detail.decay}
        />
        <MetricBar
          label="Access"
          value={`${detail.access_count} times`}
          normalized={Math.min(1, detail.access_count / 20)}
        />
        <p className="text-muted-foreground text-xs">
          Last accessed {formatTimestamp(detail.last_accessed)}
        </p>
      </div>

      <div className="space-y-2">
        <p className="text-muted-foreground text-xs uppercase tracking-wide">
          Content
        </p>
        <div className="max-h-56 overflow-y-auto rounded-md border bg-muted/20 p-3 whitespace-pre-wrap">
          {detail.content}
        </div>
      </div>

      <div className="space-y-2">
        <p className="text-muted-foreground text-xs uppercase tracking-wide">
          Emotional trace
        </p>
        <div className="grid gap-3">
          <MetricBar
            label="Valence"
            value={detail.emotional_trace.valence.toFixed(2)}
            normalized={detail.emotional_trace.valence}
          />
          <MetricBar
            label="Arousal"
            value={detail.emotional_trace.arousal.toFixed(2)}
            normalized={detail.emotional_trace.arousal}
          />
          <MetricBar
            label="Intensity"
            value={detail.emotional_trace.intensity.toFixed(2)}
            normalized={detail.emotional_trace.intensity}
          />
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <Badge variant="outline">{`importance ${detail.importance}`}</Badge>
        <Badge variant="outline">{`decay ${detail.decay.toFixed(2)}`}</Badge>
        <Badge variant="outline">{`access ${detail.access_count}`}</Badge>
        {detail.is_private ? <Badge variant="secondary">private</Badge> : null}
        {(detail.tags ?? []).map((tag) => (
          <Badge key={tag} variant="secondary">
            #{tag}
          </Badge>
        ))}
      </div>

      <div className="space-y-2">
        <p className="text-muted-foreground text-xs uppercase tracking-wide">
          Linked memories ({detail.linked_ids.length})
        </p>
        <div className="space-y-2 text-xs">
          {detail.linked_ids.length > 0 ? (
            detail.linked_ids.map((link) => (
              <div
                key={`${link.target_id}-${link.link_type}`}
                className="flex items-center justify-between gap-3 rounded-md border bg-muted/10 px-3 py-2"
              >
                <div>
                  <p className="font-medium">{link.target_id}</p>
                  <p className="text-muted-foreground uppercase">
                    {link.link_type}
                  </p>
                </div>
                <p>{link.confidence.toFixed(2)}</p>
              </div>
            ))
          ) : (
            <p>No linked memories.</p>
          )}
        </div>
      </div>

      <div className="space-y-2">
        <p className="text-muted-foreground text-xs uppercase tracking-wide">
          Generated notions ({detail.generated_notion_ids.length})
        </p>
        <div className="space-y-2 text-xs">
          {detail.generated_notion_ids.length > 0 ? (
            detail.generated_notion_ids.map((id) => (
              <div
                key={id}
                className="rounded-md border bg-muted/10 px-3 py-2 font-medium"
              >
                {id}
              </div>
            ))
          ) : (
            <p>No generated notions.</p>
          )}
        </div>
      </div>
    </CardContent>
  </Card>
)
