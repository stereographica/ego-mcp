import {
  BaseEdge,
  EdgeLabelRenderer,
  getStraightPath,
  type EdgeProps,
} from '@xyflow/react'

import {
  NOTION_SOURCE_GRADIENT_END,
  SEARCH_HIGHLIGHT_COLOR,
  getEdgeDashArray,
  getEdgeStroke,
  getEdgeStrokeWidth,
} from '@/components/memory/memory-graph-palette'

type MemoryEdgeData = {
  link_type?: string
  confidence?: number
  highlighted?: boolean
  showLabel?: boolean
}

export const MemoryEdge = ({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
  markerEnd,
}: EdgeProps) => {
  const edgeData = (data ?? {}) as MemoryEdgeData
  const [edgePath, labelX, labelY] = getStraightPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
  })
  const opacity = Math.max(0.2, edgeData.confidence ?? 0.4)
  const strokeColor = edgeData.highlighted
    ? SEARCH_HIGHLIGHT_COLOR
    : edgeData.link_type === 'notion_source'
      ? `url(#${id}-gradient)`
      : getEdgeStroke(edgeData.link_type ?? 'related')
  const strokeWidth = getEdgeStrokeWidth(
    edgeData.link_type ?? 'related',
    edgeData.confidence,
    edgeData.highlighted,
  )

  return (
    <>
      {edgeData.link_type === 'notion_source' && !edgeData.highlighted ? (
        <defs>
          <linearGradient
            id={`${id}-gradient`}
            gradientUnits="userSpaceOnUse"
            x1={sourceX}
            y1={sourceY}
            x2={targetX}
            y2={targetY}
          >
            <stop offset="0%" stopColor={getEdgeStroke('notion_source')} />
            <stop offset="100%" stopColor={NOTION_SOURCE_GRADIENT_END} />
          </linearGradient>
        </defs>
      ) : null}
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: strokeColor,
          strokeWidth,
          strokeOpacity: opacity,
          strokeDasharray: getEdgeDashArray(edgeData.link_type ?? 'related'),
        }}
      />
      {edgeData.showLabel ? (
        <EdgeLabelRenderer>
          <div
            className="border-border bg-slate-950/90 text-slate-100 pointer-events-none absolute rounded border px-1.5 py-0.5 text-[10px]"
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            }}
          >
            {edgeData.link_type}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  )
}
