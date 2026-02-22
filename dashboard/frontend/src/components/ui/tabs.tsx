import * as TabsPrimitive from '@radix-ui/react-tabs'
import type { PropsWithChildren } from 'react'

export const Tabs = TabsPrimitive.Root

export const TabsList = ({ children }: PropsWithChildren) => (
  <TabsPrimitive.List className="tab-list">{children}</TabsPrimitive.List>
)

export const TabsTrigger = ({
  value,
  children,
}: PropsWithChildren<{ value: string }>) => (
  <TabsPrimitive.Trigger className="tab-trigger" value={value}>
    {children}
  </TabsPrimitive.Trigger>
)

export const TabsContent = ({
  value,
  children,
}: PropsWithChildren<{ value: string }>) => (
  <TabsPrimitive.Content value={value}>{children}</TabsPrimitive.Content>
)
