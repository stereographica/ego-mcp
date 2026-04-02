type MemorySearchBarProps = {
  query: string
  onChange: (query: string) => void
}

export const MemorySearchBar = ({ query, onChange }: MemorySearchBarProps) => (
  <input
    type="search"
    value={query}
    onChange={(event) => onChange(event.currentTarget.value)}
    placeholder="Search memories and notions..."
    className="w-full rounded-md border bg-background px-3 py-2 text-sm"
  />
)
