import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { MemoryNetworkStats } from '@/types'

const formatPercent = (value: number) => `${Math.round(value * 100)}%`

type MemoryGraphStatsProps = {
  stats: MemoryNetworkStats
}

export const MemoryGraphStats = ({ stats }: MemoryGraphStatsProps) => (
  <Card className="min-w-0">
    <CardHeader className="pb-3">
      <CardTitle className="text-sm">Graph stats</CardTitle>
    </CardHeader>
    <CardContent className="grid gap-3 text-sm md:grid-cols-3 xl:grid-cols-7">
      <div>
        <p className="text-muted-foreground text-xs">Nodes</p>
        <p className="font-semibold">{stats.node_count}</p>
        <p className="text-muted-foreground text-xs">
          {stats.memory_count} memories / {stats.notion_count} notions
        </p>
      </div>
      <div>
        <p className="text-muted-foreground text-xs">Edges</p>
        <p className="font-semibold">{stats.edge_count}</p>
      </div>
      <div>
        <p className="text-muted-foreground text-xs">Convictions</p>
        <p className="font-semibold">
          {stats.conviction_count} / {stats.notion_count}
        </p>
      </div>
      <div>
        <p className="text-muted-foreground text-xs">Avg decay</p>
        <p className="font-semibold">{stats.avg_memory_decay.toFixed(2)}</p>
      </div>
      <div>
        <p className="text-muted-foreground text-xs">Density</p>
        <p className="font-semibold">{stats.graph_density.toFixed(3)}</p>
      </div>
      <div>
        <p className="text-muted-foreground text-xs">Top hub</p>
        <p className="font-semibold">
          {stats.top_hub_id
            ? `${stats.top_hub_id} (${stats.top_hub_degree})`
            : '-'}
        </p>
      </div>
      <div>
        <p className="text-muted-foreground text-xs">Top category</p>
        <p className="font-semibold">
          {stats.top_category
            ? `${stats.top_category} (${formatPercent(stats.top_category_ratio)})`
            : '-'}
        </p>
      </div>
    </CardContent>
  </Card>
)
