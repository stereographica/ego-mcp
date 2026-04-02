type MemorySearchBarProps = {
  query: string
  onChange: (query: string) => void
  onSubmit?: () => void
}

export const MemorySearchBar = ({
  query,
  onChange,
  onSubmit,
}: MemorySearchBarProps) => (
  <input
    type="search"
    value={query}
    onChange={(event) => onChange(event.currentTarget.value)}
    onKeyDown={(event) => {
      if (event.key === 'Enter') {
        event.preventDefault()
        onSubmit?.()
      }
    }}
    placeholder="Search memories and notions..."
    className="w-full rounded-md border bg-background px-3 py-2 text-sm"
  />
)
