import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import type { PersonOverview } from '@/types'

type PersonOverviewProps = {
  persons: PersonOverview[]
  isLoading: boolean
  onSelect: (personId: string) => void
}

const relationKindBadge = (kind: string) => {
  if (kind === 'interlocutor') {
    return (
      <Badge
        variant="outline"
        className="bg-blue-50 text-blue-700 border-blue-200"
      >
        interlocutor
      </Badge>
    )
  }
  return (
    <Badge
      variant="outline"
      className="bg-green-50 text-green-700 border-green-200"
    >
      mentioned
    </Badge>
  )
}

const trustBar = (level: number | null) => {
  if (level === null)
    return <span className="text-muted-foreground text-xs">-</span>
  const pct = Math.round(level * 100)
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-16 rounded-full bg-muted">
        <div
          className="h-2 rounded-full bg-blue-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs tabular-nums text-muted-foreground">{pct}%</span>
    </div>
  )
}

export const PersonOverviewTable = ({
  persons,
  isLoading,
  onSelect,
}: PersonOverviewProps) => {
  if (isLoading) {
    return (
      <p className="text-muted-foreground text-sm py-8 text-center">
        Loading...
      </p>
    )
  }

  if (persons.length === 0) {
    return (
      <p className="text-muted-foreground text-sm py-8 text-center">
        No relationships found. Relationships appear after using tools like{' '}
        <code className="text-xs bg-muted px-1 py-0.5 rounded">
          consider_them
        </code>{' '}
        or <code className="text-xs bg-muted px-1 py-0.5 rounded">wake_up</code>
        .
      </p>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead>Name</TableHead>
          <TableHead>Kind</TableHead>
          <TableHead>Trust</TableHead>
          <TableHead className="text-right">Interactions</TableHead>
          <TableHead className="text-right">Episodes</TableHead>
          <TableHead>Last seen</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {persons.map((p) => (
          <TableRow
            key={p.person_id}
            className="cursor-pointer hover:bg-muted/50"
            onClick={() => onSelect(p.person_id)}
          >
            <TableCell>
              <div className="flex flex-col">
                <span className="font-medium">{p.name || p.person_id}</span>
                {p.aliases.length > 0 && (
                  <span className="text-muted-foreground text-xs">
                    also: {p.aliases.slice(0, 2).join(', ')}
                    {p.aliases.length > 2 ? '...' : ''}
                  </span>
                )}
              </div>
            </TableCell>
            <TableCell>{relationKindBadge(p.relation_kind)}</TableCell>
            <TableCell>{trustBar(p.trust_level)}</TableCell>
            <TableCell className="text-right tabular-nums">
              {p.total_interactions}
            </TableCell>
            <TableCell className="text-right tabular-nums">
              {p.shared_episodes_count}
            </TableCell>
            <TableCell>
              {p.last_interaction ? (
                new Date(p.last_interaction).toLocaleDateString()
              ) : (
                <span className="text-muted-foreground text-xs">-</span>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
