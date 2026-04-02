import { useEffect, useRef, useState } from 'react'

import { Lock } from 'lucide-react'
import { Handle, Position, type NodeProps } from '@xyflow/react'

type MemoryNodeData = {
  label: string
  color: string
  textColor: string
  borderColor: string
  radius: number
  tooltipLines: string[]
  highlighted: boolean
  dimmed: boolean
  faded: boolean
  isPrivate: boolean
  recentlyAccessed: boolean
}

export const MemoryNode = ({ data, selected }: NodeProps) => {
  const nodeData = data as MemoryNodeData
  const [showTooltip, setShowTooltip] = useState(false)
  const timeoutRef = useRef<number | null>(null)

  useEffect(
    () => () => {
      if (timeoutRef.current != null) {
        window.clearTimeout(timeoutRef.current)
      }
    },
    [],
  )

  return (
    <div
      className="relative flex items-center justify-center text-center"
      style={{
        width: nodeData.radius * 2,
        height: nodeData.radius * 2,
        borderRadius: '9999px',
        background: nodeData.color,
        color: nodeData.textColor,
        opacity: nodeData.dimmed ? 0.15 : nodeData.faded ? 0.4 : 1,
        boxShadow: nodeData.highlighted
          ? '0 0 0 4px rgba(250, 204, 21, 0.65)'
          : selected
            ? '0 0 0 3px rgba(255, 255, 255, 0.8)'
            : '0 12px 20px rgba(15, 23, 42, 0.18)',
        border: `2px solid ${nodeData.borderColor}`,
        fontSize: Math.max(10, Math.min(12, nodeData.radius / 1.8)),
        fontWeight: 600,
        padding: 6,
      }}
      onMouseEnter={() => {
        if (timeoutRef.current != null) {
          window.clearTimeout(timeoutRef.current)
        }
        timeoutRef.current = window.setTimeout(() => setShowTooltip(true), 200)
      }}
      onMouseLeave={() => {
        if (timeoutRef.current != null) {
          window.clearTimeout(timeoutRef.current)
        }
        setShowTooltip(false)
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
      {nodeData.recentlyAccessed ? (
        <span className="memory-node-pulse pointer-events-none absolute inset-[-6px] rounded-full" />
      ) : null}
      <span className="line-clamp-3 break-words">{nodeData.label}</span>
      {nodeData.isPrivate ? (
        <span className="absolute -right-1 -top-1 rounded-full bg-slate-950/80 p-1 text-[10px] text-slate-50">
          <Lock className="h-3 w-3" />
        </span>
      ) : null}
      {showTooltip ? (
        <div className="bg-popover text-popover-foreground pointer-events-none absolute -top-3 left-1/2 z-30 min-w-48 max-w-64 -translate-x-1/2 -translate-y-full rounded-lg border px-3 py-2 text-left text-[11px] leading-relaxed shadow-xl">
          {nodeData.tooltipLines.map((line) => (
            <p key={line}>{line}</p>
          ))}
        </div>
      ) : null}
    </div>
  )
}
