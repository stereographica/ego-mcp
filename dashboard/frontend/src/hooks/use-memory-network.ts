import { useCallback, useEffect, useState } from 'react'

import {
  fetchMemoryDetail,
  fetchMemoryNetwork,
  fetchMemoryPath,
  fetchMemorySubgraph,
} from '@/api'
import type {
  MemoryDetail,
  MemoryNetworkPath,
  MemoryNetworkResponse,
} from '@/types'

const EMPTY_NETWORK: MemoryNetworkResponse = {
  nodes: [],
  edges: [],
  stats: {
    node_count: 0,
    memory_count: 0,
    notion_count: 0,
    edge_count: 0,
    conviction_count: 0,
    avg_memory_decay: 0,
    graph_density: 0,
    top_hub_degree: 0,
    top_category_ratio: 0,
  },
}

const EMPTY_PATH: MemoryNetworkPath = {
  node_ids: [],
  edge_pairs: [],
  length: 0,
  exists: false,
}

type UseMemoryNetworkResult = {
  loading: boolean
  fullNetwork?: MemoryNetworkResponse
  network: MemoryNetworkResponse
  path: MemoryNetworkPath
  loadPath: (from: string, to: string) => Promise<MemoryNetworkPath>
  loadFullGraph: () => Promise<MemoryNetworkResponse>
  loadSubgraph: (
    nodeId: string,
    depth?: number,
  ) => Promise<MemoryNetworkResponse>
  loadDetail: (memoryId: string) => Promise<MemoryDetail | null>
  clearPath: () => void
}

export const useMemoryNetwork = (active = true): UseMemoryNetworkResult => {
  const [loading, setLoading] = useState(false)
  const [fullNetwork, setFullNetwork] =
    useState<MemoryNetworkResponse>(EMPTY_NETWORK)
  const [network, setNetwork] = useState<MemoryNetworkResponse>(EMPTY_NETWORK)
  const [path, setPath] = useState<MemoryNetworkPath>(EMPTY_PATH)

  useEffect(() => {
    if (!active) return

    let disposed = false
    setLoading(true)
    void fetchMemoryNetwork().then((nextNetwork) => {
      if (disposed) return
      setFullNetwork(nextNetwork)
      setNetwork(nextNetwork)
      setLoading(false)
    })

    return () => {
      disposed = true
    }
  }, [active])

  const loadSubgraph = useCallback(async (nodeId: string, depth = 1) => {
    setLoading(true)
    const subgraph = await fetchMemorySubgraph(nodeId, depth)
    setNetwork(subgraph)
    setPath(EMPTY_PATH)
    setLoading(false)
    return subgraph
  }, [])

  const loadFullGraph = useCallback(async () => {
    if (fullNetwork.nodes.length > 0) {
      setNetwork(fullNetwork)
      setPath(EMPTY_PATH)
      return fullNetwork
    }

    setLoading(true)
    const nextNetwork = await fetchMemoryNetwork()
    setFullNetwork(nextNetwork)
    setNetwork(nextNetwork)
    setPath(EMPTY_PATH)
    setLoading(false)
    return nextNetwork
  }, [fullNetwork])

  const loadPath = useCallback(async (from: string, to: string) => {
    const nextPath = await fetchMemoryPath(from, to)
    const resolvedPath = nextPath.exists ? nextPath : EMPTY_PATH
    setPath(resolvedPath)
    return resolvedPath
  }, [])

  const loadDetail = useCallback(
    async (memoryId: string) => fetchMemoryDetail(memoryId),
    [],
  )

  const clearPath = useCallback(() => {
    setPath(EMPTY_PATH)
  }, [])

  return {
    loading,
    fullNetwork,
    network,
    path,
    loadPath,
    loadFullGraph,
    loadSubgraph,
    loadDetail,
    clearPath,
  }
}
