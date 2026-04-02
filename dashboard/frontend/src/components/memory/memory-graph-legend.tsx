import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

import {
  CONVICTION_RING_COLOR,
  MEMORY_CATEGORY_COLORS,
  MEMORY_CATEGORY_ORDER,
  NOTION_TONE_COLORS,
  SEARCH_HIGHLIGHT_COLOR,
  getEdgeStroke,
} from '@/components/memory/memory-graph-palette'

type MemoryGraphLegendProps = {
  categories?: string[]
}

const NodeSwatch = ({
  shape,
  fill,
  border,
  label,
}: {
  shape: 'circle' | 'hexagon'
  fill: string
  border: string
  label: string
}) => (
  <div className="flex items-center gap-2">
    <span
      className="inline-block h-4 w-4 shrink-0"
      style={{
        background: fill,
        border: `2px solid ${border}`,
        borderRadius: shape === 'circle' ? '9999px' : undefined,
        clipPath:
          shape === 'hexagon'
            ? 'polygon(25% 0%, 75% 0%, 100% 50%, 75% 100%, 25% 100%, 0% 50%)'
            : undefined,
      }}
    />
    <span>{label}</span>
  </div>
)

const EdgeSwatch = ({
  label,
  color,
  dashArray,
}: {
  label: string
  color: string
  dashArray?: string
}) => (
  <div className="flex items-center gap-2">
    <span
      className="inline-block w-8 shrink-0 border-t-2"
      style={{
        borderColor: color,
        borderTopStyle: dashArray ? 'dashed' : 'solid',
      }}
    />
    <span>{label}</span>
  </div>
)

export const MemoryGraphLegend = ({
  categories = MEMORY_CATEGORY_ORDER as unknown as string[],
}: MemoryGraphLegendProps) => {
  const categoryItems =
    categories.length > 0
      ? categories
      : (MEMORY_CATEGORY_ORDER as unknown as string[])

  return (
    <Card className="min-w-0">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">Legend</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 text-xs md:grid-cols-2 xl:grid-cols-4">
        <div className="space-y-2">
          <p className="text-muted-foreground font-medium uppercase tracking-wide">
            Node types
          </p>
          <NodeSwatch
            shape="circle"
            fill={MEMORY_CATEGORY_COLORS.TECHNICAL}
            border="rgba(248, 250, 252, 0.8)"
            label="Memory node"
          />
          <NodeSwatch
            shape="hexagon"
            fill={NOTION_TONE_COLORS.neutral}
            border="rgba(248, 250, 252, 0.8)"
            label="Notion node"
          />
          <NodeSwatch
            shape="hexagon"
            fill={NOTION_TONE_COLORS.positive}
            border={CONVICTION_RING_COLOR}
            label="Conviction"
          />
          <div className="flex items-center gap-2">
            <span
              className="inline-block h-4 w-4 rounded-full border-2"
              style={{
                borderColor: SEARCH_HIGHLIGHT_COLOR,
                background: 'transparent',
              }}
            />
            <span>Search / path highlight</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-slate-400 text-[9px]">
              L
            </span>
            <span>Private memory lock</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-block h-4 w-4 rounded-full bg-slate-200 opacity-40" />
            <span>Low-decay memory</span>
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-muted-foreground font-medium uppercase tracking-wide">
            Memory categories
          </p>
          <div className="grid gap-1">
            {categoryItems.map((category) => (
              <div key={category} className="flex items-center gap-2">
                <span
                  className="inline-block h-3 w-3 rounded-full"
                  style={{
                    background:
                      MEMORY_CATEGORY_COLORS[category.toUpperCase()] ??
                      MEMORY_CATEGORY_COLORS.MEMORY,
                  }}
                />
                <span>{category}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-muted-foreground font-medium uppercase tracking-wide">
            Notion tones
          </p>
          <div className="grid gap-1">
            <div className="flex items-center gap-2">
              <span
                className="inline-block h-3 w-3 rounded-full"
                style={{ background: NOTION_TONE_COLORS.positive }}
              />
              <span>Positive</span>
            </div>
            <div className="flex items-center gap-2">
              <span
                className="inline-block h-3 w-3 rounded-full"
                style={{ background: NOTION_TONE_COLORS.negative }}
              />
              <span>Negative</span>
            </div>
            <div className="flex items-center gap-2">
              <span
                className="inline-block h-3 w-3 rounded-full"
                style={{ background: NOTION_TONE_COLORS.neutral }}
              />
              <span>Neutral / mixed</span>
            </div>
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-muted-foreground font-medium uppercase tracking-wide">
            Edge types
          </p>
          <EdgeSwatch
            label="SIMILAR / RELATED"
            color={getEdgeStroke('related')}
          />
          <EdgeSwatch label="CAUSED_BY" color={getEdgeStroke('caused_by')} />
          <EdgeSwatch label="LEADS_TO" color={getEdgeStroke('leads_to')} />
          <EdgeSwatch
            label="Memory → Notion"
            color={getEdgeStroke('notion_source')}
          />
          <EdgeSwatch
            label="Notion ↔ Notion"
            color={getEdgeStroke('notion_related')}
            dashArray="6 4"
          />
        </div>
      </CardContent>
    </Card>
  )
}
