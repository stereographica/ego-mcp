import {
  BaseEdge,
  EdgeLabelRenderer,
  getStraightPath,
  type EdgeProps,
} from '@xyflow/react'

type MemoryEdgeData = {
  link_type?: string
  confidence?: number
  highlighted?: boolean
  showLabel?: boolean
}

const strokeFor = (linkType?: string) => {
  switch (linkType) {
    case 'caused_by':
      return 'hsl(0 65% 55%)'
    case 'leads_to':
      return 'hsl(145 55% 45%)'
    case 'notion_source':
      return 'hsl(270 60% 55%)'
    case 'notion_related':
      return 'hsl(45 90% 50%)'
    default:
      return 'hsl(0 0% 60%)'
  }
}

const dashArrayFor = (linkType?: string) => {
  switch (linkType) {
    case 'related':
      return '4 4'
    case 'notion_related':
      return '6 4'
    default:
      return undefined
  }
}

export const MemoryEdge = ({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
}: EdgeProps) => {
  const edgeData = (data ?? {}) as MemoryEdgeData
  const [edgePath, labelX, labelY] = getStraightPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
  })
  const opacity = Math.max(0.2, edgeData.confidence ?? 0.4)
  const strokeWidth =
    edgeData.link_type === 'notion_source' ||
    edgeData.link_type === 'notion_related'
      ? Math.max(2, (edgeData.confidence ?? 0.5) * 4)
      : Math.max(1, (edgeData.confidence ?? 0.3) * 4)

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: strokeFor(edgeData.link_type),
          strokeWidth: edgeData.highlighted ? strokeWidth + 1.5 : strokeWidth,
          strokeOpacity: opacity,
          strokeDasharray: dashArrayFor(edgeData.link_type),
        }}
      />
      {edgeData.showLabel ? (
        <EdgeLabelRenderer>
          <div
            className="border-border bg-background pointer-events-none absolute rounded border px-1.5 py-0.5 text-[10px]"
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
