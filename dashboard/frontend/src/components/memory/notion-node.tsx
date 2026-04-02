import { Handle, Position, type NodeProps } from '@xyflow/react'

type NotionNodeData = {
  label: string
  color: string
  radius: number
  tooltip: string
  highlighted: boolean
  dimmed: boolean
  faded: boolean
  conviction: boolean
}

export const NotionNode = ({ data, selected }: NodeProps) => {
  const nodeData = data as NotionNodeData

  return (
    <div
      className="relative flex items-center justify-center text-center"
      style={{
        width: nodeData.radius * 2,
        height: nodeData.radius * 2,
        clipPath:
          'polygon(25% 0%, 75% 0%, 100% 50%, 75% 100%, 25% 100%, 0% 50%)',
        background: nodeData.color,
        color: 'white',
        opacity: nodeData.dimmed ? 0.15 : nodeData.faded ? 0.45 : 1,
        boxShadow: nodeData.highlighted
          ? '0 0 0 4px rgba(250, 204, 21, 0.65)'
          : selected
            ? '0 0 0 3px rgba(255, 255, 255, 0.8)'
            : '0 12px 20px rgba(15, 23, 42, 0.18)',
        border: nodeData.conviction
          ? '3px solid rgba(250, 204, 21, 0.9)'
          : '2px solid rgba(255, 255, 255, 0.75)',
        fontSize: Math.max(10, Math.min(12, nodeData.radius / 1.8)),
        fontWeight: 600,
        padding: 8,
      }}
      title={nodeData.tooltip}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
      <span className="line-clamp-3 break-words">{nodeData.label}</span>
    </div>
  )
}
