import type { PropsWithChildren } from 'react'

type CardProps = PropsWithChildren<{
  className?: string
}>

export const Card = ({ children, className }: CardProps) => (
  <section className={className ? `card ${className}` : 'card'}>
    {children}
  </section>
)
