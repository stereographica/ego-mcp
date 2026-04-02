import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { MemoryNetworkNode } from '@/types'

type NotionDetailPanelProps = {
  notion: MemoryNetworkNode
  relatedNotionIds: string[]
  sourceMemoryIds: string[]
}

const formatTimestamp = (value?: string | null) =>
  value ? new Date(value).toLocaleString() : 'n/a'

export const NotionDetailPanel = ({
  notion,
  relatedNotionIds,
  sourceMemoryIds,
}: NotionDetailPanelProps) => (
  <Card className="h-full">
    <CardHeader>
      <CardTitle className="text-sm">Notion detail</CardTitle>
    </CardHeader>
    <CardContent className="space-y-4 text-sm">
      <div className="space-y-1">
        <p className="font-medium">{notion.label ?? notion.id}</p>
        <p className="text-muted-foreground text-xs">
          {`${formatTimestamp(notion.created)} -> ${formatTimestamp(
            notion.last_reinforced,
          )}`}
        </p>
      </div>

      <p className="text-muted-foreground text-xs uppercase tracking-wide">
        Confidence
      </p>
      <div className="flex flex-wrap gap-2">
        <Badge variant="outline">{`Confidence ${(notion.confidence ?? 0).toFixed(2)}`}</Badge>
        <Badge variant="outline">
          {`Reinforced ${notion.reinforcement_count ?? 0}`}
        </Badge>
        <Badge variant="outline">{`Sources ${notion.source_count ?? 0}`}</Badge>
        {notion.is_conviction ? (
          <Badge variant="secondary">conviction</Badge>
        ) : null}
        {notion.person_id ? (
          <Badge variant="outline">{notion.person_id}</Badge>
        ) : null}
      </div>

      <div className="flex flex-wrap gap-2">
        {(notion.tags ?? []).map((tag) => (
          <Badge key={tag} variant="secondary">
            #{tag}
          </Badge>
        ))}
      </div>

      <div className="space-y-2">
        <p className="text-muted-foreground text-xs uppercase tracking-wide">
          Source memories
        </p>
        <div className="space-y-1 text-xs">
          {sourceMemoryIds.length > 0 ? (
            sourceMemoryIds.map((id) => <p key={id}>{id}</p>)
          ) : (
            <p>No source memories.</p>
          )}
        </div>
      </div>

      <div className="space-y-2">
        <p className="text-muted-foreground text-xs uppercase tracking-wide">
          Related notions
        </p>
        <div className="space-y-1 text-xs">
          {relatedNotionIds.length > 0 ? (
            relatedNotionIds.map((id) => <p key={id}>{id}</p>)
          ) : (
            <p>No related notions.</p>
          )}
        </div>
      </div>
    </CardContent>
  </Card>
)
