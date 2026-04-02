import { useEffect, useMemo, useState } from 'react'

import { MemoryDetailPanel } from '@/components/memory/memory-detail-panel'
import { MemoryFilterPanel } from '@/components/memory/memory-filter-panel'
import { MemoryGraph } from '@/components/memory/memory-graph'
import { MemoryGraphStats } from '@/components/memory/memory-graph-stats'
import {
  DEFAULT_MEMORY_GRAPH_FILTERS,
  applyMemoryGraphFilters,
} from '@/components/memory/memory-graph-utils'
import { MemorySearchBar } from '@/components/memory/memory-search-bar'
import { NotionDetailPanel } from '@/components/memory/notion-detail-panel'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useMemoryNetwork } from '@/hooks/use-memory-network'
import type { MemoryDetail, MemoryNetworkNode } from '@/types'

type MemoryTabProps = {
  isActive?: boolean
}

type LayoutMode = 'force' | 'hierarchical' | 'radial'

export const MemoryTab = ({ isActive = true }: MemoryTabProps) => {
  const {
    network,
    loading,
    path,
    loadFullGraph,
    loadSubgraph,
    loadDetail,
    loadPath,
    clearPath,
  } = useMemoryNetwork(isActive)
  const [filters, setFilters] = useState(DEFAULT_MEMORY_GRAPH_FILTERS)
  const [query, setQuery] = useState('')
  const [selectedNode, setSelectedNode] = useState<MemoryNetworkNode | null>(
    null,
  )
  const [selectedDetail, setSelectedDetail] = useState<MemoryDetail | null>(
    null,
  )
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null)
  const [pathStartId, setPathStartId] = useState<string | null>(null)
  const [pathEndId, setPathEndId] = useState<string | null>(null)
  const [radialDepth, setRadialDepth] = useState(2)
  const [layout, setLayout] = useState<LayoutMode>('force')
  const [showEdgeLabels, setShowEdgeLabels] = useState(false)
  const [pinnedPositions, setPinnedPositions] = useState<
    Record<string, { x: number; y: number }>
  >({})

  const filteredNetwork = useMemo(
    () => applyMemoryGraphFilters(network, filters),
    [filters, network],
  )

  const categories = useMemo(
    () =>
      Array.from(
        new Set(
          network.nodes
            .filter((node) => !node.is_notion)
            .map((node) => node.category)
            .filter((category): category is string => Boolean(category)),
        ),
      ).sort(),
    [network.nodes],
  )

  useEffect(() => {
    if (!selectedNode || selectedNode.is_notion) {
      setSelectedDetail(null)
      return
    }

    let cancelled = false
    const run = async () => {
      const detail = await loadDetail(selectedNode.id)
      if (!cancelled) {
        setSelectedDetail(detail)
      }
    }

    void run()
    return () => {
      cancelled = true
    }
  }, [loadDetail, selectedNode])

  useEffect(() => {
    if (!pathStartId || !pathEndId || pathStartId === pathEndId) {
      clearPath()
      return
    }
    void loadPath(pathStartId, pathEndId)
  }, [clearPath, loadPath, pathEndId, pathStartId])

  useEffect(() => {
    if (layout !== 'radial' || !focusedNodeId) return
    void loadSubgraph(focusedNodeId, radialDepth)
  }, [focusedNodeId, layout, loadSubgraph, radialDepth])

  const relatedNotionIds = useMemo(() => {
    if (!selectedNode?.is_notion) return []
    const related = new Set<string>()
    for (const edge of network.edges) {
      if (edge.source === selectedNode.id) {
        const target = network.nodes.find((node) => node.id === edge.target)
        if (target?.is_notion) related.add(target.id)
      }
      if (edge.target === selectedNode.id) {
        const source = network.nodes.find((node) => node.id === edge.source)
        if (source?.is_notion) related.add(source.id)
      }
    }
    return [...related].sort()
  }, [network.edges, network.nodes, selectedNode])

  const sourceMemoryIds = useMemo(() => {
    if (!selectedNode?.is_notion) return []
    const sources = new Set<string>()
    for (const edge of network.edges) {
      if (edge.target !== selectedNode.id) continue
      const source = network.nodes.find((node) => node.id === edge.source)
      if (source && !source.is_notion) sources.add(source.id)
    }
    return [...sources].sort()
  }, [network.edges, network.nodes, selectedNode])

  const handleFocusNeighborhood = async (nodeId: string) => {
    setFocusedNodeId(nodeId)
    setLayout('radial')
  }

  const handleResetFocus = async () => {
    setFocusedNodeId(null)
    setLayout('force')
    await loadFullGraph()
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
        <div className="space-y-4">
          <MemoryFilterPanel
            filters={filters}
            categories={categories}
            onChange={setFilters}
          />
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Search</CardTitle>
            </CardHeader>
            <CardContent>
              <MemorySearchBar query={query} onChange={setQuery} />
            </CardContent>
          </Card>
        </div>
        <MemoryGraphStats stats={filteredNetwork.stats} />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <Card className="min-w-0 overflow-hidden">
          <CardHeader className="flex flex-row items-start justify-between gap-4">
            <div>
              <CardTitle>Memory graph</CardTitle>
              <p className="text-muted-foreground mt-1 text-sm">
                Explore memories and notions across the full graph.
              </p>
            </div>
            <div className="text-muted-foreground text-xs">
              {loading
                ? 'Loading graph...'
                : `${filteredNetwork.nodes.length} nodes`}
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {layout === 'radial' && focusedNodeId ? (
              <label className="block space-y-2 text-sm">
                <span>{`Neighborhood depth ${radialDepth}`}</span>
                <input
                  className="w-full"
                  type="range"
                  min={1}
                  max={3}
                  step={1}
                  value={radialDepth}
                  onChange={(event) =>
                    setRadialDepth(Number(event.currentTarget.value))
                  }
                />
              </label>
            ) : null}

            {pathStartId || pathEndId ? (
              <div className="text-muted-foreground rounded-md border bg-muted/20 px-3 py-2 text-xs">
                {`Path: ${pathStartId ?? '...'} -> ${pathEndId ?? '...'}`}
                {path?.exists ? ` (${path.length} hops)` : ''}
              </div>
            ) : null}

            {filteredNetwork.nodes.length > 0 ? (
              <MemoryGraph
                network={filteredNetwork}
                selectedNodeId={selectedNode?.id ?? null}
                focusedNodeId={focusedNodeId}
                searchQuery={query}
                path={path}
                pinnedPositions={pinnedPositions}
                layout={layout}
                showEdgeLabels={showEdgeLabels}
                onLayoutChange={setLayout}
                onShowEdgeLabelsChange={setShowEdgeLabels}
                onSelectNode={setSelectedNode}
                onFocusNeighborhood={handleFocusNeighborhood}
                onResetFocus={handleResetFocus}
                onSetPathStart={setPathStartId}
                onSetPathEnd={setPathEndId}
                onPinNode={(nodeId, point) =>
                  setPinnedPositions((current) => ({
                    ...current,
                    [nodeId]: point,
                  }))
                }
              />
            ) : (
              <div className="text-muted-foreground flex h-[320px] items-center justify-center rounded-lg border border-dashed text-sm">
                No nodes match the current filter.
              </div>
            )}
          </CardContent>
        </Card>

        <div className="min-w-0">
          {selectedNode ? (
            selectedNode.is_notion ? (
              <NotionDetailPanel
                notion={selectedNode}
                relatedNotionIds={relatedNotionIds}
                sourceMemoryIds={sourceMemoryIds}
              />
            ) : selectedDetail ? (
              <MemoryDetailPanel detail={selectedDetail} />
            ) : (
              <Card className="h-full">
                <CardHeader>
                  <CardTitle className="text-sm">Detail panel</CardTitle>
                </CardHeader>
                <CardContent className="text-muted-foreground text-sm">
                  Loading memory detail...
                </CardContent>
              </Card>
            )
          ) : (
            <Card className="h-full">
              <CardHeader>
                <CardTitle className="text-sm">Detail panel</CardTitle>
              </CardHeader>
              <CardContent className="text-muted-foreground text-sm">
                Click a node to inspect memory or notion details.
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
