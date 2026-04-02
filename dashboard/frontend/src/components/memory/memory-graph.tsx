import { useEffect, useMemo, useState } from 'react'

import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  useReactFlow,
  type Edge,
  type EdgeTypes,
  type Node,
  type NodeMouseHandler,
  type NodeTypes,
} from '@xyflow/react'

import {
  calcMemoryNodeRadius,
  calcNotionNodeRadius,
  nodeMatchesQuery,
} from '@/components/memory/memory-graph-utils'
import {
  getEdgeStroke,
  getNodeBorderColor,
  getNodeFillColor,
  getNodeTextColor,
  wasAccessedRecently,
} from '@/components/memory/memory-graph-palette'
import { MemoryEdge } from './memory-edge'
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
  textColor: string
  borderColor: string
  radius: number
  tooltipLines: string[]
  highlighted: boolean
  dimmed: boolean
  faded: boolean
  conviction: boolean
  isPrivate: boolean
  recentlyAccessed: boolean
}

type MemoryGraphProps = {
  network: MemoryNetworkResponse
  selectedNodeId?: string | null
  focusedNodeId?: string | null
  searchFocusNodeId?: string | null
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

const edgeTypes = { memory: MemoryEdge } as EdgeTypes

const pathEdgeKey = (source: string, target: string) => `${source}->${target}`

const buildNodeTooltipLines = (node: MemoryNetworkNode) => {
  if (node.is_notion) {
    return [
      node.is_conviction ? '[CONVICTION]' : 'Notion',
      node.label ?? node.id,
      `Confidence: ${(node.confidence ?? 0).toFixed(2)}`,
      `Reinforced: ${node.reinforcement_count ?? 0}`,
      `Sources: ${node.source_count ?? 0}`,
      node.emotion_tone ? `Emotion: ${node.emotion_tone}` : null,
    ].filter((line): line is string => Boolean(line))
  }

  return [
    node.category,
    node.content_preview ?? node.label ?? node.id,
    `Importance: ${node.importance ?? 0}`,
    `Decay: ${(node.decay ?? 0).toFixed(2)}`,
    `Access: ${node.access_count ?? 0}`,
    `Links: ${node.degree}`,
    node.tags && node.tags.length > 0
      ? `Tags: ${node.tags.map((tag) => `#${tag}`).join(' ')}`
      : null,
  ].filter((line): line is string => Boolean(line))
}

const ViewportController = ({
  targetNodeId,
  positions,
}: {
  targetNodeId: string | null
  positions: Map<string, { x: number; y: number }>
}) => {
  const { setCenter } = useReactFlow()

  useEffect(() => {
    if (!targetNodeId) return
    const point = positions.get(targetNodeId)
    if (!point) return
    void setCenter(point.x, point.y, {
      zoom: 1.15,
      duration: 350,
    })
  }, [positions, setCenter, targetNodeId])

  return null
}

export const MemoryGraph = ({
  network,
  selectedNodeId,
  focusedNodeId,
  searchFocusNodeId,
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
      const fillColor = getNodeFillColor(node)
      const textColor = getNodeTextColor(fillColor)
      return {
        id: node.id,
        type: node.is_notion ? 'notion' : 'memory',
        position,
        draggable: false,
        selected: node.id === selectedNodeId,
        data: {
          label: node.label ?? node.id,
          color: fillColor,
          textColor,
          borderColor: getNodeBorderColor(node, fillColor),
          radius: node.is_notion
            ? calcNotionNodeRadius(node)
            : calcMemoryNodeRadius(node),
          tooltipLines: buildNodeTooltipLines(node),
          highlighted,
          dimmed: hasSearch && !matchingIds.has(node.id),
          faded: !node.is_notion && (node.decay ?? 1) < 0.3,
          conviction: Boolean(node.is_conviction),
          isPrivate: Boolean(node.is_private),
          recentlyAccessed:
            !node.is_notion && wasAccessedRecently(node.last_accessed),
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
          type: 'memory',
          source: edge.source,
          target: edge.target,
          markerEnd: directed
            ? {
                type: MarkerType.ArrowClosed,
                color: isPathEdge ? '#f59e0b' : getEdgeStroke(edge.link_type),
              }
            : undefined,
          data: {
            link_type: edge.link_type,
            confidence: edge.confidence,
            highlighted: isPathEdge,
            showLabel: showEdgeLabels,
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
    <div className="memory-graph-surface relative min-w-0 overflow-hidden rounded-xl border bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800">
      <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3 text-sm">
        <label className="flex items-center gap-2">
          <span className="text-slate-400 text-xs">Layout</span>
          <select
            value={layout}
            className="h-8 rounded-md border border-slate-700 bg-slate-950/70 px-2 text-sm text-slate-100"
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
            className="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-100 hover:bg-slate-800"
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
          edgeTypes={edgeTypes}
          onNodeClick={handleNodeClick}
          onNodeDoubleClick={handleNodeDoubleClick}
          onNodeContextMenu={handleNodeContextMenu}
          nodesConnectable={false}
          elementsSelectable
          proOptions={{ hideAttribution: true }}
        >
          <ViewportController
            targetNodeId={
              searchFocusNodeId ?? selectedNodeId ?? focusedNodeId ?? null
            }
            positions={positions}
          />
          <MiniMap
            zoomable
            pannable
            bgColor="rgba(2, 6, 23, 0.95)"
            maskColor="rgba(2, 6, 23, 0.7)"
            nodeColor={(node) => String(node.data?.color ?? '#94a3b8')}
          />
          <Controls />
          <Background color="rgba(148, 163, 184, 0.15)" gap={18} />
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
