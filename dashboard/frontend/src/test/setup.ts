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

// ResizeObserver polyfill for jsdom
globalThis.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

// scrollIntoView polyfill for jsdom
Element.prototype.scrollIntoView = function () {}
