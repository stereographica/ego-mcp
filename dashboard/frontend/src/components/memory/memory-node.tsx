import { Lock } from 'lucide-react'
import { Handle, Position, type NodeProps } from '@xyflow/react'

type MemoryNodeData = {
  label: string
  color: string
  radius: number
  tooltip: string
  highlighted: boolean
  dimmed: boolean
  faded: boolean
  isPrivate: boolean
}

export const MemoryNode = ({ data, selected }: NodeProps) => {
  const nodeData = data as MemoryNodeData

  return (
    <div
      className="relative flex items-center justify-center text-center"
      style={{
        width: nodeData.radius * 2,
        height: nodeData.radius * 2,
        borderRadius: '9999px',
        background: nodeData.color,
        color: 'white',
        opacity: nodeData.dimmed ? 0.15 : nodeData.faded ? 0.4 : 1,
        boxShadow: nodeData.highlighted
          ? '0 0 0 4px rgba(250, 204, 21, 0.65)'
          : selected
            ? '0 0 0 3px rgba(255, 255, 255, 0.8)'
            : '0 12px 20px rgba(15, 23, 42, 0.18)',
        border: '2px solid rgba(255, 255, 255, 0.75)',
        fontSize: Math.max(10, Math.min(12, nodeData.radius / 1.8)),
        fontWeight: 600,
        padding: 6,
      }}
      title={nodeData.tooltip}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
      <span className="line-clamp-3 break-words">{nodeData.label}</span>
      {nodeData.isPrivate ? (
        <span className="absolute -right-1 -top-1 rounded-full bg-black/70 p-1 text-[10px]">
          <Lock className="h-3 w-3" />
        </span>
      ) : null}
    </div>
  )
}
