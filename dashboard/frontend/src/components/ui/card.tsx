import type { PropsWithChildren } from 'react'

export const Card = ({ children }: PropsWithChildren) => (
  <section className="card">{children}</section>
)
