import { useMemo } from 'react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import type { MemoryNetworkResponse } from '@/types'

type MemoryNetworkPanelProps = {
  network: MemoryNetworkResponse
}

const CATEGORY_COLORS = [
  'var(--color-chart-1)',
  'var(--color-chart-2)',
  'var(--color-chart-3)',
  'var(--color-chart-4)',
  'var(--color-chart-5)',
  'var(--color-chart-6)',
]

const hashString = (value: string) =>
  Array.from(value).reduce(
    (acc, char) => ((acc << 5) - acc + char.charCodeAt(0)) | 0,
    0,
  )

export const MemoryNetworkPanel = ({ network }: MemoryNetworkPanelProps) => {
  const { positionedNodes, positionedEdges, nodeRadius } = useMemo(() => {
    const center = 160
    const radius = 110
    const sortedNodes = [...network.nodes].sort((lhs, rhs) => {
      const lhsScore = (lhs.access_count ?? 0) + (lhs.confidence ?? 0) * 10
      const rhsScore = (rhs.access_count ?? 0) + (rhs.confidence ?? 0) * 10
      return rhsScore - lhsScore
    })
    const nodeRadius =
      sortedNodes.length > 0 ? 18 / Math.sqrt(sortedNodes.length) : 10
    const positionedNodes = sortedNodes.map((node, index) => {
      const angle =
        sortedNodes.length === 1
          ? 0
          : (index / sortedNodes.length) * Math.PI * 2
      const ring = index === 0 ? 0 : radius
      return {
        ...node,
        x: center + Math.cos(angle) * ring,
        y: center + Math.sin(angle) * ring,
        r: Math.max(
          5,
          Math.min(16, nodeRadius + (node.access_count ?? 0) * 0.8),
        ),
        color:
          CATEGORY_COLORS[
            Math.abs(hashString(node.category)) % CATEGORY_COLORS.length
          ],
      }
    })
    const positionedEdges = network.edges
      .map((edge) => ({
        ...edge,
        sourceNode: positionedNodes.find((node) => node.id === edge.source),
        targetNode: positionedNodes.find((node) => node.id === edge.target),
      }))
      .filter((edge) => edge.sourceNode && edge.targetNode)
    return { positionedNodes, positionedEdges, nodeRadius }
  }, [network])

  return (
    <Card className="min-w-0 overflow-hidden">
      <CardHeader>
        <CardTitle className="text-sm">Memory network</CardTitle>
      </CardHeader>
      <CardContent className="min-w-0 space-y-3">
        <div className="min-w-0 overflow-hidden rounded-lg border border-border/60 bg-muted/20 p-2">
          <svg
            viewBox="0 0 320 320"
            className="h-[320px] w-full max-w-full"
            role="img"
            aria-label="Memory network graph"
          >
            {positionedEdges.map((edge) => {
              const opacity = Math.max(
                0.2,
                Math.min(0.9, edge.confidence ?? 0.4),
              )
              const strokeWidth = Math.max(1, (edge.confidence ?? 0.3) * 3)
              return (
                <line
                  key={`${edge.source}-${edge.target}-${edge.link_type}`}
                  x1={edge.sourceNode?.x ?? 0}
                  y1={edge.sourceNode?.y ?? 0}
                  x2={edge.targetNode?.x ?? 0}
                  y2={edge.targetNode?.y ?? 0}
                  stroke="var(--color-muted-foreground)"
                  strokeOpacity={opacity}
                  strokeWidth={strokeWidth}
                >
                  <title>{`${edge.link_type} (${edge.source} -> ${edge.target})`}</title>
                </line>
              )
            })}
            {positionedNodes.map((node) => (
              <g key={node.id}>
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={node.r}
                  fill={node.is_notion ? 'var(--color-chart-4)' : node.color}
                  fillOpacity={
                    node.is_notion ? 0.75 : Math.max(0.35, node.decay ?? 0.5)
                  }
                  stroke="var(--color-background)"
                  strokeWidth={2}
                >
                  <title>
                    {[
                      node.id,
                      node.label,
                      node.category,
                      node.is_notion ? 'notion' : 'memory',
                    ]
                      .filter(Boolean)
                      .join(' - ')}
                  </title>
                </circle>
                {node.is_notion ? (
                  <text
                    x={node.x}
                    y={node.y - node.r - 4}
                    textAnchor="middle"
                    className="fill-muted-foreground text-[10px]"
                  >
                    {node.label ?? node.id}
                  </text>
                ) : null}
              </g>
            ))}
            {positionedNodes.length === 0 ? (
              <text
                x="50%"
                y="50%"
                textAnchor="middle"
                className="fill-muted-foreground text-sm"
              >
                No memory network data
              </text>
            ) : null}
          </svg>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <Badge variant="outline">nodes {network.nodes.length}</Badge>
          <Badge variant="outline">edges {network.edges.length}</Badge>
          <Badge variant="outline">radius {nodeRadius.toFixed(1)}</Badge>
        </div>
        <ScrollArea className="h-[140px] min-w-0 rounded-md border">
          <div className="divide-y">
            {[...network.nodes]
              .sort(
                (lhs, rhs) =>
                  (rhs.access_count ?? 0) - (lhs.access_count ?? 0) ||
                  (rhs.confidence ?? 0) - (lhs.confidence ?? 0),
              )
              .slice(0, 12)
              .map((node) => (
                <div
                  key={node.id}
                  className="flex items-center justify-between gap-3 px-3 py-2 text-xs"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium">
                      {node.label ?? node.id}
                    </p>
                    <p className="text-muted-foreground truncate">
                      {node.category}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Badge variant="secondary">
                      {node.is_notion ? 'notion' : 'memory'}
                    </Badge>
                    <span className="text-muted-foreground">
                      {(node.confidence ?? node.decay ?? 0).toFixed(2)}
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
