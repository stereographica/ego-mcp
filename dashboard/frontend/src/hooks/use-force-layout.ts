import { useMemo } from 'react'

import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
} from 'd3-force'

import {
  calcMemoryNodeRadius,
  calcNotionNodeRadius,
} from '@/components/memory/memory-graph-utils'
import type { MemoryNetworkResponse } from '@/types'

type LayoutMode = 'force' | 'hierarchical' | 'radial'

type LayoutPoint = {
  x: number
  y: number
}

type LayoutSimulationNode = {
  id: string
  radius: number
  x?: number
  y?: number
  fx?: number
  fy?: number
}

type LayoutSimulationLink = {
  source: string | LayoutSimulationNode
  target: string | LayoutSimulationNode
  confidence?: number
  isNotionLink?: boolean
}

type UseForceLayoutOptions = {
  network: MemoryNetworkResponse
  layout: LayoutMode
  focusNodeId?: string | null
  pinnedPositions?: Record<string, LayoutPoint>
  width?: number
  height?: number
}

const fallbackPoint = (
  index: number,
  total: number,
  width: number,
  height: number,
) => {
  const angle = total <= 1 ? 0 : (index / total) * Math.PI * 2
  const radius = Math.min(width, height) * 0.28
  return {
    x: width / 2 + Math.cos(angle) * radius,
    y: height / 2 + Math.sin(angle) * radius,
  }
}

const buildAdjacency = (network: MemoryNetworkResponse) => {
  const adjacency = new Map<string, Set<string>>()
  for (const node of network.nodes) {
    adjacency.set(node.id, new Set())
  }
  for (const edge of network.edges) {
    adjacency.get(edge.source)?.add(edge.target)
    adjacency.get(edge.target)?.add(edge.source)
  }
  return adjacency
}

const radialLayout = (
  network: MemoryNetworkResponse,
  focusNodeId: string,
  width: number,
  height: number,
) => {
  const adjacency = buildAdjacency(network)
  const depthById = new Map<string, number>([[focusNodeId, 0]])
  const queue = [focusNodeId]
  while (queue.length > 0) {
    const current = queue.shift()
    if (current == null) continue
    const depth = depthById.get(current) ?? 0
    for (const neighbor of adjacency.get(current) ?? []) {
      if (depthById.has(neighbor)) continue
      depthById.set(neighbor, depth + 1)
      queue.push(neighbor)
    }
  }

  const nodesByDepth = new Map<number, string[]>()
  for (const node of network.nodes) {
    const depth = depthById.get(node.id)
    if (depth == null) continue
    const list = nodesByDepth.get(depth) ?? []
    list.push(node.id)
    nodesByDepth.set(depth, list)
  }

  const positions = new Map<string, LayoutPoint>()
  positions.set(focusNodeId, { x: width / 2, y: height / 2 })
  const ringStep = Math.min(width, height) * 0.16
  for (const [depth, ids] of nodesByDepth.entries()) {
    if (depth === 0) continue
    ids.forEach((id, index) => {
      const angle = (index / ids.length) * Math.PI * 2
      positions.set(id, {
        x: width / 2 + Math.cos(angle) * ringStep * depth,
        y: height / 2 + Math.sin(angle) * ringStep * depth,
      })
    })
  }
  return positions
}

const hierarchicalLayout = (
  network: MemoryNetworkResponse,
  width: number,
  height: number,
) => {
  const notionNodes = network.nodes.filter((node) => node.is_notion)
  const memoryNodes = network.nodes.filter((node) => !node.is_notion)
  const positions = new Map<string, LayoutPoint>()
  const place = (ids: string[], y: number) => {
    ids.forEach((id, index) => {
      const x = ((index + 1) * width) / (ids.length + 1)
      positions.set(id, { x, y })
    })
  }
  place(
    notionNodes.map((node) => node.id),
    height * 0.25,
  )
  place(
    memoryNodes.map((node) => node.id),
    height * 0.72,
  )
  return positions
}

export const useForceLayout = ({
  network,
  layout,
  focusNodeId,
  pinnedPositions = {},
  width = 860,
  height = 640,
}: UseForceLayoutOptions) =>
  useMemo(() => {
    if (network.nodes.length === 0) return new Map<string, LayoutPoint>()
    const nodeById = new Map(network.nodes.map((node) => [node.id, node]))

    if (layout === 'hierarchical') {
      return hierarchicalLayout(network, width, height)
    }

    if (layout === 'radial' && focusNodeId) {
      return radialLayout(network, focusNodeId, width, height)
    }

    const simulationNodes: LayoutSimulationNode[] = network.nodes.map(
      (node, index) => {
        const pinned = pinnedPositions[node.id]
        const fallback = fallbackPoint(
          index,
          network.nodes.length,
          width,
          height,
        )
        return {
          id: node.id,
          radius: node.is_notion
            ? calcNotionNodeRadius(node)
            : calcMemoryNodeRadius(node),
          x: pinned?.x ?? fallback.x,
          y: pinned?.y ?? fallback.y,
          fx: pinned?.x,
          fy: pinned?.y,
        }
      },
    )

    const simulationLinks: LayoutSimulationLink[] = network.edges.map(
      (edge) => ({
        source: edge.source,
        target: edge.target,
        confidence: edge.confidence ?? 0.5,
        isNotionLink:
          nodeById.get(edge.source)?.is_notion === true ||
          nodeById.get(edge.target)?.is_notion === true,
      }),
    )

    const simulation = forceSimulation(simulationNodes)
      .force(
        'link',
        forceLink(simulationLinks)
          .id((node: LayoutSimulationNode) => String(node.id))
          .distance((link: LayoutSimulationLink) => {
            const baseDistance = link.isNotionLink ? 96 : 132
            return baseDistance - (link.confidence ?? 0.5) * 48
          })
          .strength((link: LayoutSimulationLink) =>
            Math.min(1, 0.18 + (link.confidence ?? 0.5) * 0.7),
          ),
      )
      .force('charge', forceManyBody().strength(-280))
      .force(
        'collide',
        forceCollide().radius((node: LayoutSimulationNode) => node.radius + 18),
      )
      .force(
        'x',
        forceX((node: LayoutSimulationNode) => {
          const source = nodeById.get(node.id)
          return source?.is_notion ? width / 2 : width / 2 + 24
        }).strength((node: LayoutSimulationNode) => {
          const source = nodeById.get(node.id)
          return source?.is_notion ? 0.08 : 0.03
        }),
      )
      .force(
        'y',
        forceY((node: LayoutSimulationNode) => {
          const source = nodeById.get(node.id)
          return source?.is_notion ? height * 0.42 : height * 0.58
        }).strength((node: LayoutSimulationNode) => {
          const source = nodeById.get(node.id)
          return source?.is_notion ? 0.06 : 0.025
        }),
      )
      .force('center', forceCenter(width / 2, height / 2))
      .stop()

    for (let tick = 0; tick < 250; tick += 1) {
      simulation.tick()
    }

    return new Map(
      simulationNodes.map((node) => [
        node.id,
        {
          x: node.x ?? width / 2,
          y: node.y ?? height / 2,
        },
      ]),
    )
  }, [focusNodeId, height, layout, network, pinnedPositions, width])
