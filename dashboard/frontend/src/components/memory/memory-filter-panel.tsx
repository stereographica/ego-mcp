import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { MemoryGraphFilters } from '@/types'

import { DEFAULT_MEMORY_GRAPH_FILTERS } from '@/components/memory/memory-graph-utils'

type MemoryFilterPanelProps = {
  filters: MemoryGraphFilters
  categories: string[]
  onChange: (filters: MemoryGraphFilters) => void
}

export const MemoryFilterPanel = ({
  filters,
  categories,
  onChange,
}: MemoryFilterPanelProps) => (
  <Card className="min-w-0">
    <CardHeader className="pb-3">
      <CardTitle className="text-sm">Filter panel</CardTitle>
    </CardHeader>
    <CardContent className="space-y-4 text-sm">
      <label className="flex items-center gap-2">
        <input
          aria-label="Memories"
          type="checkbox"
          checked={filters.showMemories}
          onChange={(event) =>
            onChange({ ...filters, showMemories: event.target.checked })
          }
        />
        <span>Memories</span>
      </label>
      <label className="flex items-center gap-2">
        <input
          aria-label="Notions"
          type="checkbox"
          checked={filters.showNotions}
          onChange={(event) =>
            onChange({ ...filters, showNotions: event.target.checked })
          }
        />
        <span>Notions</span>
      </label>
      <label className="flex items-center gap-2">
        <input
          aria-label="Convictions only"
          type="checkbox"
          checked={filters.convictionsOnly}
          onChange={(event) =>
            onChange({ ...filters, convictionsOnly: event.target.checked })
          }
        />
        <span>Convictions only</span>
      </label>

      <div className="space-y-2">
        <span className="text-xs font-medium">Category</span>
        <div className="space-y-2 rounded-md border p-3">
          {categories.length > 0 ? (
            categories.map((category) => {
              const checked = filters.categories.includes(category)
              return (
                <label key={category} className="flex items-center gap-2">
                  <input
                    aria-label={`Category ${category}`}
                    type="checkbox"
                    checked={checked}
                    onChange={() =>
                      onChange({
                        ...filters,
                        categories: checked
                          ? filters.categories.filter(
                              (item) => item !== category,
                            )
                          : [...filters.categories, category].sort(),
                      })
                    }
                  />
                  <span>{category}</span>
                </label>
              )
            })
          ) : (
            <p className="text-muted-foreground text-xs">All categories</p>
          )}
        </div>
      </div>

      <label className="space-y-2">
        <span className="text-xs font-medium">
          Importance {filters.minImportance}
        </span>
        <input
          type="range"
          min={1}
          max={5}
          value={filters.minImportance}
          onChange={(event) =>
            onChange({
              ...filters,
              minImportance: Number(event.target.value),
            })
          }
          className="w-full"
        />
      </label>

      <label className="space-y-2">
        <span className="text-xs font-medium">
          Confidence {filters.minConfidence.toFixed(1)}
        </span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.1}
          value={filters.minConfidence}
          onChange={(event) =>
            onChange({
              ...filters,
              minConfidence: Number(event.target.value),
            })
          }
          className="w-full"
        />
      </label>

      <label className="space-y-2">
        <span className="text-xs font-medium">
          Decay {filters.minDecay.toFixed(1)}
        </span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.1}
          value={filters.minDecay}
          onChange={(event) =>
            onChange({
              ...filters,
              minDecay: Number(event.target.value),
            })
          }
          className="w-full"
        />
      </label>

      <button
        type="button"
        className="border-input hover:bg-muted w-full rounded-md border px-3 py-2 text-sm"
        onClick={() => onChange(DEFAULT_MEMORY_GRAPH_FILTERS)}
      >
        Reset filters
      </button>
    </CardContent>
  </Card>
)
