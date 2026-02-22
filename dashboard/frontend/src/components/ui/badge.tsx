import type { PropsWithChildren } from 'react'

export const Badge = ({ children }: PropsWithChildren) => (
  <span className="badge">{children}</span>
)
