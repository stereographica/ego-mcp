import { useMemo, useState } from 'react'

import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler,
  type NodeTypes,
} from '@xyflow/react'

import {
  calcMemoryNodeRadius,
  calcNotionNodeRadius,
  nodeMatchesQuery,
} from '@/components/memory/memory-graph-utils'
import { MemoryNode } from './memory-node'
import { NotionNode } from './notion-node'
import { useForceLayout } from '@/hooks/use-force-layout'
import type {
  MemoryNetworkNode,
  MemoryNetworkPath,
  MemoryNetworkResponse,
} from '@/types'

type LayoutMode = 'force' | 'hierarchical' | 'radial'

type GraphNodeData = {
  label: string
  color: string
  radius: number
  tooltip: string
  highlighted: boolean
  dimmed: boolean
  faded: boolean
  conviction: boolean
  isPrivate: boolean
}

type MemoryGraphProps = {
  network: MemoryNetworkResponse
  selectedNodeId?: string | null
  focusedNodeId?: string | null
  searchQuery: string
  path: MemoryNetworkPath | null
  pinnedPositions: Record<string, { x: number; y: number }>
  layout: LayoutMode
  showEdgeLabels: boolean
  onLayoutChange: (layout: LayoutMode) => void
  onShowEdgeLabelsChange: (value: boolean) => void
  onSelectNode: (node: MemoryNetworkNode) => void
  onFocusNeighborhood: (nodeId: string) => void
  onResetFocus: () => void
  onSetPathStart: (nodeId: string) => void
  onSetPathEnd: (nodeId: string) => void
  onPinNode: (nodeId: string, point: { x: number; y: number }) => void
}

const nodeTypes = {
  memory: MemoryNode,
  notion: NotionNode,
} as NodeTypes

const categoryColor = (node: MemoryNetworkNode) => {
  if (node.is_notion) {
    if (node.is_conviction) {
      return 'hsl(45, 90%, 50%)'
    }
    switch ((node.emotion_tone ?? '').toLowerCase()) {
      case 'joy':
      case 'excited':
      case 'moved':
      case 'grateful':
      case 'proud':
      case 'hopeful':
        return 'hsl(48, 82%, 55%)'
      case 'sad':
      case 'anxious':
      case 'frustrated':
      case 'angry':
      case 'lonely':
      case 'ashamed':
        return 'hsl(212, 62%, 50%)'
      default:
        return 'hsl(172, 46%, 46%)'
    }
  }
  switch (node.category.toUpperCase()) {
    case 'DAILY':
      return 'hsl(210, 70%, 55%)'
    case 'PHILOSOPHICAL':
      return 'hsl(270, 60%, 55%)'
    case 'TECHNICAL':
      return 'hsl(145, 55%, 45%)'
    case 'FEELING':
      return 'hsl(0, 65%, 55%)'
    case 'RELATIONSHIP':
      return 'hsl(30, 70%, 55%)'
    case 'OBSERVATION':
      return 'hsl(185, 55%, 45%)'
    case 'CONVERSATION':
      return 'hsl(50, 65%, 50%)'
    case 'INTROSPECTION':
      return 'hsl(310, 55%, 50%)'
    case 'SELF_DISCOVERY':
      return 'hsl(240, 50%, 60%)'
    case 'DREAM':
      return 'hsl(160, 45%, 50%)'
    case 'LESSON':
      return 'hsl(90, 50%, 45%)'
    default:
      return 'hsl(0, 0%, 60%)'
  }
}

const pathEdgeKey = (source: string, target: string) => `${source}->${target}`

const edgeStroke = (linkType: string) => {
  switch (linkType) {
    case 'caused_by':
      return 'hsl(0, 65%, 55%)'
    case 'leads_to':
      return 'hsl(145, 55%, 45%)'
    case 'notion_source':
      return 'hsl(270, 60%, 55%)'
    case 'notion_related':
      return 'hsl(45, 90%, 50%)'
    default:
      return 'hsl(0, 0%, 60%)'
  }
}

const edgeDashArray = (linkType: string) => {
  switch (linkType) {
    case 'related':
      return '4 4'
    case 'notion_related':
      return '6 4'
    default:
      return undefined
  }
}

const buildNodeTooltip = (node: MemoryNetworkNode) => {
  if (node.is_notion) {
    return [
      node.is_conviction ? '[CONVICTION]' : 'Notion',
      node.label ?? node.id,
      `Confidence: ${(node.confidence ?? 0).toFixed(2)}`,
      `Reinforced: ${node.reinforcement_count ?? 0}`,
      `Sources: ${node.source_count ?? 0}`,
      node.emotion_tone ? `Emotion: ${node.emotion_tone}` : null,
    ]
      .filter(Boolean)
      .join('\n')
  }

  return [
    node.category,
    node.content_preview ?? node.label ?? node.id,
    `Importance: ${node.importance ?? 0}`,
    `Decay: ${(node.decay ?? 0).toFixed(2)}`,
    `Access: ${node.access_count ?? 0}`,
    node.tags && node.tags.length > 0
      ? `Tags: ${node.tags.map((tag) => `#${tag}`).join(' ')}`
      : null,
  ]
    .filter(Boolean)
    .join('\n')
}

export const MemoryGraph = ({
  network,
  selectedNodeId,
  focusedNodeId,
  searchQuery,
  path,
  pinnedPositions,
  layout,
  showEdgeLabels,
  onLayoutChange,
  onShowEdgeLabelsChange,
  onSelectNode,
  onFocusNeighborhood,
  onResetFocus,
  onSetPathStart,
  onSetPathEnd,
  onPinNode,
}: MemoryGraphProps) => {
  const [contextMenu, setContextMenu] = useState<{
    node: MemoryNetworkNode
    x: number
    y: number
  } | null>(null)

  const positions = useForceLayout({
    network,
    layout,
    focusNodeId: focusedNodeId,
    pinnedPositions,
  })

  const matchingIds = useMemo(
    () =>
      new Set(
        network.nodes
          .filter((node) => nodeMatchesQuery(node, searchQuery))
          .map((node) => node.id),
      ),
    [network.nodes, searchQuery],
  )

  const pathEdges = useMemo(() => {
    const keys = new Set<string>()
    for (const [source, target] of path?.edge_pairs ?? []) {
      keys.add(pathEdgeKey(source, target))
      keys.add(pathEdgeKey(target, source))
    }
    return keys
  }, [path?.edge_pairs])

  const flowNodes = useMemo<Node<GraphNodeData>[]>(() => {
    const hasSearch = searchQuery.trim().length > 0
    return network.nodes.map((node, index) => {
      const position =
        positions.get(node.id) ??
        ({
          x: 160 + index * 24,
          y: 160 + index * 12,
        } as const)
      const highlighted =
        matchingIds.has(node.id) ||
        path?.node_ids.includes(node.id) ||
        node.id === focusedNodeId
      return {
        id: node.id,
        type: node.is_notion ? 'notion' : 'memory',
        position,
        draggable: false,
        selected: node.id === selectedNodeId,
        data: {
          label: node.label ?? node.id,
          color: categoryColor(node),
          radius: node.is_notion
            ? calcNotionNodeRadius(node)
            : calcMemoryNodeRadius(node),
          tooltip: buildNodeTooltip(node),
          highlighted,
          dimmed: hasSearch && !matchingIds.has(node.id),
          faded: !node.is_notion && (node.decay ?? 1) < 0.3,
          conviction: Boolean(node.is_conviction),
          isPrivate: Boolean(node.is_private),
        },
      }
    })
  }, [
    focusedNodeId,
    matchingIds,
    network.nodes,
    path?.node_ids,
    positions,
    searchQuery,
    selectedNodeId,
  ])

  const flowEdges = useMemo<Edge[]>(
    () =>
      network.edges.map((edge, index) => {
        const isPathEdge = pathEdges.has(pathEdgeKey(edge.source, edge.target))
        const directed = !['related', 'similar', 'notion_related'].includes(
          edge.link_type,
        )
        return {
          id: `${edge.source}-${edge.target}-${edge.link_type}-${index}`,
          source: edge.source,
          target: edge.target,
          label: showEdgeLabels ? edge.link_type : undefined,
          markerEnd: directed
            ? {
                type: MarkerType.ArrowClosed,
                color: isPathEdge ? '#f59e0b' : edgeStroke(edge.link_type),
              }
            : undefined,
          style: {
            stroke: isPathEdge ? '#f59e0b' : edgeStroke(edge.link_type),
            strokeWidth: isPathEdge
              ? 3
              : Math.max(1.5, (edge.confidence ?? 0.3) * 4),
            strokeDasharray: edgeDashArray(edge.link_type),
            opacity: Math.max(0.2, edge.confidence ?? 0.4),
          },
          labelStyle: {
            fontSize: 11,
            fill: '#475569',
          },
        }
      }),
    [network.edges, pathEdges, showEdgeLabels],
  )

  const handleNodeClick: NodeMouseHandler = (_event, flowNode) => {
    const node = network.nodes.find((candidate) => candidate.id === flowNode.id)
    if (node) {
      onSelectNode(node)
    }
    setContextMenu(null)
  }

  const handleNodeDoubleClick: NodeMouseHandler = (_event, flowNode) => {
    onFocusNeighborhood(flowNode.id)
    setContextMenu(null)
  }

  const handleNodeContextMenu: NodeMouseHandler = (event, flowNode) => {
    event.preventDefault()
    const node = network.nodes.find((candidate) => candidate.id === flowNode.id)
    if (!node) return
    setContextMenu({
      node,
      x: event.clientX,
      y: event.clientY,
    })
  }

  return (
    <div className="relative min-w-0 overflow-hidden rounded-xl border bg-gradient-to-br from-white via-slate-50 to-amber-50">
      <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3 text-sm">
        <label className="flex items-center gap-2">
          <span className="text-muted-foreground text-xs">Layout</span>
          <select
            value={layout}
            className="border-input bg-background h-8 rounded-md border px-2 text-sm"
            onChange={(event) =>
              onLayoutChange(event.currentTarget.value as LayoutMode)
            }
          >
            <option value="force">Force-directed</option>
            <option value="hierarchical">Hierarchical</option>
            <option value="radial">Radial</option>
          </select>
        </label>

        <label className="ml-auto flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={showEdgeLabels}
            onChange={(event) =>
              onShowEdgeLabelsChange(event.currentTarget.checked)
            }
          />
          <span>Show edge labels</span>
        </label>

        {focusedNodeId ? (
          <button
            type="button"
            className="border-input hover:bg-muted rounded-md border px-3 py-1.5 text-xs"
            onClick={onResetFocus}
          >
            Return to full graph
          </button>
        ) : null}
      </div>

      <div className="h-[640px] w-full" onClick={() => setContextMenu(null)}>
        <ReactFlow
          fitView
          nodes={flowNodes}
          edges={flowEdges}
          nodeTypes={nodeTypes}
          onNodeClick={handleNodeClick}
          onNodeDoubleClick={handleNodeDoubleClick}
          onNodeContextMenu={handleNodeContextMenu}
          nodesConnectable={false}
          elementsSelectable
          proOptions={{ hideAttribution: true }}
        >
          <MiniMap zoomable pannable />
          <Controls />
          <Background color="#e2e8f0" gap={18} />
        </ReactFlow>
      </div>

      {contextMenu ? (
        <div
          className="bg-popover text-popover-foreground absolute z-20 min-w-44 rounded-lg border p-1 shadow-lg"
          style={{
            left: contextMenu.x,
            top: contextMenu.y,
            transform: 'translate(-12px, 8px)',
          }}
        >
          <button
            type="button"
            className="hover:bg-muted flex w-full rounded-md px-3 py-2 text-left text-sm"
            onClick={() => {
              const point = positions.get(contextMenu.node.id)
              if (point) {
                onPinNode(contextMenu.node.id, point)
              }
              setContextMenu(null)
            }}
          >
            Pin this node
          </button>
          <button
            type="button"
            className="hover:bg-muted flex w-full rounded-md px-3 py-2 text-left text-sm"
            onClick={() => {
              onFocusNeighborhood(contextMenu.node.id)
              onLayoutChange('radial')
              setContextMenu(null)
            }}
          >
            Show neighborhood
          </button>
          <button
            type="button"
            className="hover:bg-muted flex w-full rounded-md px-3 py-2 text-left text-sm"
            onClick={() => {
              onSetPathStart(contextMenu.node.id)
              setContextMenu(null)
            }}
          >
            Set path start
          </button>
          <button
            type="button"
            className="hover:bg-muted flex w-full rounded-md px-3 py-2 text-left text-sm"
            onClick={() => {
              onSetPathEnd(contextMenu.node.id)
              setContextMenu(null)
            }}
          >
            Set path end
          </button>
        </div>
      ) : null}
    </div>
  )
}
