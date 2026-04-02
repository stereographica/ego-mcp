import type {
  MemoryGraphFilters,
  MemoryNetworkEdge,
  MemoryNetworkNode,
  MemoryNetworkResponse,
  MemoryNetworkStats,
} from '@/types'

const clamp = (value: number, min: number, max: number) =>
  Math.max(min, Math.min(max, value))

export const DEFAULT_MEMORY_GRAPH_FILTERS: MemoryGraphFilters = {
  showMemories: true,
  showNotions: true,
  convictionsOnly: false,
  categories: [],
  minImportance: 1,
  minConfidence: 0,
  minDecay: 0,
}

export const calcMemoryNodeRadius = (node: MemoryNetworkNode): number => {
  const score =
    (node.importance ?? 1) * 4 +
    Math.log2((node.access_count ?? 0) + 1) * 3 +
    node.degree * 2 +
    (node.decay ?? 0.5) * 5
  return clamp(score, 8, 32)
}

export const calcNotionNodeRadius = (node: MemoryNetworkNode): number => {
  const score =
    (node.confidence ?? 0) * 8 +
    (node.reinforcement_count ?? 0) * 1.5 +
    (node.source_count ?? 0) * 2 +
    node.degree
  return clamp(score, 10, 40)
}

const filterNode = (node: MemoryNetworkNode, filters: MemoryGraphFilters) => {
  if (!filters.showMemories && !node.is_notion) return false
  if (!filters.showNotions && node.is_notion) return false
  if (filters.convictionsOnly && !node.is_conviction) return false
  if (!node.is_notion && filters.categories.length > 0) {
    if (!filters.categories.includes(node.category)) return false
  }
  if (!node.is_notion && (node.importance ?? 0) < filters.minImportance) {
    return false
  }
  if (node.is_notion && (node.confidence ?? 0) < filters.minConfidence) {
    return false
  }
  if (!node.is_notion && (node.decay ?? 0) < filters.minDecay) {
    return false
  }
  return true
}

const buildStats = (
  nodes: MemoryNetworkNode[],
  edges: MemoryNetworkEdge[],
): MemoryNetworkStats => {
  const memoryNodes = nodes.filter((node) => !node.is_notion)
  const notionNodes = nodes.filter((node) => node.is_notion)
  const topHub = [...nodes].sort(
    (left, right) =>
      right.degree - left.degree || left.id.localeCompare(right.id),
  )[0]
  const categoryCounts = new Map<string, number>()
  for (const node of memoryNodes) {
    categoryCounts.set(
      node.category,
      (categoryCounts.get(node.category) ?? 0) + 1,
    )
  }
  const topCategoryEntry = [...categoryCounts.entries()].sort(
    (left, right) => right[1] - left[1] || left[0].localeCompare(right[0]),
  )[0]

  return {
    node_count: nodes.length,
    memory_count: memoryNodes.length,
    notion_count: notionNodes.length,
    edge_count: edges.length,
    conviction_count: notionNodes.filter((node) => node.is_conviction).length,
    avg_memory_decay:
      memoryNodes.length > 0
        ? memoryNodes.reduce((sum, node) => sum + (node.decay ?? 0), 0) /
          memoryNodes.length
        : 0,
    graph_density:
      nodes.length > 1
        ? (2 * edges.length) / (nodes.length * (nodes.length - 1))
        : 0,
    top_hub_id: topHub?.id,
    top_hub_degree: topHub?.degree ?? 0,
    top_category: topCategoryEntry?.[0],
    top_category_ratio:
      topCategoryEntry && memoryNodes.length > 0
        ? topCategoryEntry[1] / memoryNodes.length
        : 0,
  }
}

export const applyMemoryGraphFilters = (
  network: MemoryNetworkResponse,
  filters: MemoryGraphFilters,
): MemoryNetworkResponse => {
  const nodes = network.nodes.filter((node) => filterNode(node, filters))
  const nodeIds = new Set(nodes.map((node) => node.id))
  const edges = network.edges.filter(
    (edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target),
  )
  return {
    nodes,
    edges,
    stats: buildStats(nodes, edges),
  }
}

export const nodeMatchesQuery = (node: MemoryNetworkNode, query: string) => {
  const normalized = query.trim().toLowerCase()
  if (!normalized) return true
  const haystack = node.is_notion
    ? [node.label, ...(node.tags ?? [])].filter(Boolean).join(' ')
    : [node.content_preview, ...(node.tags ?? [])].filter(Boolean).join(' ')
  return haystack.toLowerCase().includes(normalized)
}
