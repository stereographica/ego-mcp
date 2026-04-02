import '@testing-library/jest-dom'
import * as React from 'react'
import { vi } from 'vitest'

vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts')

  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => {
      if (React.isValidElement(children)) {
        return React.cloneElement(
          children as React.ReactElement<{ width?: number; height?: number }>,
          { width: 800, height: 300 },
        )
      }

      return children
    },
  }
})

vi.mock('@xyflow/react', async () => {
  const React = await vi.importActual<typeof import('react')>('react')

  return {
    ReactFlow: ({ children }: { children?: React.ReactNode }) =>
      React.createElement('div', { 'data-testid': 'react-flow' }, children),
    Background: () => null,
    Controls: () => null,
    MiniMap: () => null,
    Handle: () => null,
    BaseEdge: () => null,
    EdgeLabelRenderer: ({ children }: { children?: React.ReactNode }) =>
      children,
    getStraightPath: () => ['M0 0L1 1', 0, 0],
    MarkerType: {
      ArrowClosed: 'arrowclosed',
    },
    Position: {
      Top: 'top',
      Bottom: 'bottom',
      Left: 'left',
      Right: 'right',
    },
  }
})

// ResizeObserver polyfill for jsdom
globalThis.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

// scrollIntoView polyfill for jsdom
Element.prototype.scrollIntoView = function () {}
