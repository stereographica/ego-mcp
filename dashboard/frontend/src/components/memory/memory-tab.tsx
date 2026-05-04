import { useEffect, useMemo, useState } from 'react'

import { MemoryDetailPanel } from '@/components/memory/memory-detail-panel'
import { MemoryFilterPanel } from '@/components/memory/memory-filter-panel'
import { MemoryGraph } from '@/components/memory/memory-graph'
import { MemoryGraphLegend } from '@/components/memory/memory-graph-legend'
import { MemoryGraphStats } from '@/components/memory/memory-graph-stats'
import {
  DEFAULT_MEMORY_GRAPH_FILTERS,
  applyMemoryGraphFilters,
  nodeMatchesQuery,
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
    fullNetwork,
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
  const [searchMatchIndex, setSearchMatchIndex] = useState(-1)
  const [searchFocusNodeId, setSearchFocusNodeId] = useState<string | null>(
    null,
  )
  const [pinnedPositions, setPinnedPositions] = useState<
    Record<string, { x: number; y: number }>
  >({})

  const baseNetwork = useMemo(
    () => (fullNetwork && fullNetwork.nodes.length > 0 ? fullNetwork : network),
    [fullNetwork, network],
  )

  const filteredNetwork = useMemo(
    () => applyMemoryGraphFilters(network, filters),
    [filters, network],
  )

  const categories = useMemo(
    () =>
      Array.from(
        new Set(
          baseNetwork.nodes
            .filter((node) => !node.is_notion)
            .map((node) => node.category)
            .filter((category): category is string => Boolean(category)),
        ),
      ).sort(),
    [baseNetwork.nodes],
  )

  const searchMatches = useMemo(
    () =>
      filteredNetwork.nodes
        .filter((node) => nodeMatchesQuery(node, query))
        .sort((left, right) =>
          (left.label ?? left.content_preview ?? left.id).localeCompare(
            right.label ?? right.content_preview ?? right.id,
          ),
        ),
    [filteredNetwork.nodes, query],
  )

  const visibleMemoryCount = filteredNetwork.nodes.filter(
    (node) => !node.is_notion,
  ).length
  const visibleNotionCount = filteredNetwork.nodes.filter(
    (node) => node.is_notion,
  ).length
  const memorySourceUnavailable =
    baseNetwork.stats.memory_count === 0 && baseNetwork.stats.notion_count > 0

  useEffect(() => {
    setSearchMatchIndex(-1)
    setSearchFocusNodeId(null)
  }, [query])

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
    for (const edge of baseNetwork.edges) {
      if (edge.link_type !== 'notion_related') continue
      if (edge.source === selectedNode.id) {
        const target = baseNetwork.nodes.find((node) => node.id === edge.target)
        if (target?.is_notion) related.add(target.id)
      }
      if (edge.target === selectedNode.id) {
        const source = baseNetwork.nodes.find((node) => node.id === edge.source)
        if (source?.is_notion) related.add(source.id)
      }
    }
    return [...related].sort()
  }, [baseNetwork.edges, baseNetwork.nodes, selectedNode])

  const sourceMemoryIds = useMemo(() => {
    if (!selectedNode?.is_notion) return []
    const sources = new Set<string>()
    for (const edge of baseNetwork.edges) {
      if (edge.target !== selectedNode.id) continue
      const source = baseNetwork.nodes.find((node) => node.id === edge.source)
      if (source && !source.is_notion) sources.add(source.id)
    }
    return [...sources].sort()
  }, [baseNetwork.edges, baseNetwork.nodes, selectedNode])

  const handleSearchSubmit = () => {
    if (searchMatches.length === 0) return
    const nextIndex = (searchMatchIndex + 1) % searchMatches.length
    const nextNode = searchMatches[nextIndex]
    setSearchMatchIndex(nextIndex)
    setSearchFocusNodeId(nextNode.id)
    setSelectedNode(nextNode)
  }

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
            <CardContent className="space-y-2">
              <MemorySearchBar
                query={query}
                onChange={setQuery}
                onSubmit={handleSearchSubmit}
              />
              <p className="text-muted-foreground text-xs">
                {query.trim().length > 0
                  ? `${searchMatches.length} matches. Press Enter to focus the next node.`
                  : 'Search memory previews, notion labels, and tags.'}
              </p>
            </CardContent>
          </Card>
        </div>
        <div className="space-y-4">
          <MemoryGraphStats stats={baseNetwork.stats} />
          <MemoryGraphLegend categories={categories} />
        </div>
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
                : `Visible ${filteredNetwork.nodes.length} nodes (${visibleMemoryCount} memories / ${visibleNotionCount} notions)`}
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {memorySourceUnavailable ? (
              <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
                The current graph contains notions but no memory nodes. This
                usually means the dashboard could not read ego-mcp memory
                storage, so the full Memory graph from the design doc is not
                available yet.
              </div>
            ) : null}
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
                searchFocusNodeId={searchFocusNodeId}
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
                onNotionClick={(notionId) => {
                  const notionNode = baseNetwork.nodes.find(
                    (n) => n.id === notionId,
                  )
                  if (notionNode) {
                    setSelectedNode(notionNode)
                  }
                }}
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
