import { useMemo } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  CartesianGrid,
  XAxis,
  YAxis,
} from 'recharts'

import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatTooltipTimestampLabel } from '@/components/relationships/tooltip-utils'
import { useTimestampFormatter } from '@/hooks/use-timestamp-formatter'
import type { PersonDetail } from '@/types'

type PersonDetailPanelProps = {
  detail: PersonDetail
  onClose: () => void
}

const trustConfig: ChartConfig = {
  trust: {
    label: 'Trust level',
    color: '#3b82f6',
  },
}

const episodeConfig: ChartConfig = {
  episodes: {
    label: 'Shared episodes',
    color: '#10b981',
  },
}

const surfaceConfig: ChartConfig = {
  resonant: {
    label: 'Resonant',
    color: '#3b82f6',
  },
  involuntary: {
    label: 'Involuntary',
    color: '#f59e0b',
  },
}

export const PersonDetailPanel = ({
  detail,
  onClose,
}: PersonDetailPanelProps) => {
  const { formatTs } = useTimestampFormatter()
  const formatTooltipLabel = (label: unknown) =>
    formatTooltipTimestampLabel(label, formatTs)
  const trustData = useMemo(
    () =>
      detail.trust_history.map((pt) => ({
        ts: pt.ts,
        trust: pt.value,
      })),
    [detail.trust_history],
  )

  const episodeData = useMemo(
    () =>
      detail.shared_episodes_history.map((pt) => ({
        ts: pt.ts,
        episodes: pt.value,
      })),
    [detail.shared_episodes_history],
  )

  const surfaceData = useMemo(
    () => [
      { type: 'resonant', count: detail.surface_counts.resonant },
      { type: 'involuntary', count: detail.surface_counts.involuntary },
    ],
    [detail.surface_counts.resonant, detail.surface_counts.involuntary],
  )

  return (
    <div className="mt-4 min-w-0 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-medium">
          {detail.person_id} — detail
          <button
            onClick={onClose}
            className="ml-2 text-muted-foreground hover:text-foreground"
          >
            close
          </button>
        </h3>
      </div>

      <div className="grid gap-4 lg:grid-cols-2 [&>*]:min-w-0">
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle className="text-sm">Trust level</CardTitle>
          </CardHeader>
          <CardContent>
            {trustData.length > 0 ? (
              <ChartContainer config={trustConfig} className="h-[200px] w-full">
                <AreaChart data={trustData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="ts" hide />
                  <YAxis domain={[0, 1]} />
                  <ChartTooltip
                    content={
                      <ChartTooltipContent
                        indicator="dot"
                        labelFormatter={formatTooltipLabel}
                      />
                    }
                  />
                  <Area
                    type="monotone"
                    dataKey="trust"
                    stroke={trustConfig.trust.color}
                    fill={trustConfig.trust.color}
                    fillOpacity={0.3}
                  />
                </AreaChart>
              </ChartContainer>
            ) : (
              <p className="text-muted-foreground text-sm py-4 text-center">
                No trust data
              </p>
            )}
          </CardContent>
        </Card>

        <Card className="min-w-0">
          <CardHeader>
            <CardTitle className="text-sm">Shared episodes</CardTitle>
          </CardHeader>
          <CardContent>
            {episodeData.length > 0 ? (
              <ChartContainer
                config={episodeConfig}
                className="h-[200px] w-full"
              >
                <AreaChart data={episodeData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="ts" hide />
                  <YAxis />
                  <ChartTooltip
                    content={
                      <ChartTooltipContent
                        indicator="dot"
                        labelFormatter={formatTooltipLabel}
                      />
                    }
                  />
                  <Area
                    type="monotone"
                    dataKey="episodes"
                    stroke={episodeConfig.episodes.color}
                    fill={episodeConfig.episodes.color}
                    fillOpacity={0.3}
                  />
                </AreaChart>
              </ChartContainer>
            ) : (
              <p className="text-muted-foreground text-sm py-4 text-center">
                No episode data
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="min-w-0">
        <CardHeader>
          <CardTitle className="text-sm">Surface frequency</CardTitle>
        </CardHeader>
        <CardContent>
          {detail.surface_counts.total > 0 ? (
            <ChartContainer config={surfaceConfig} className="h-[200px] w-full">
              <BarChart data={surfaceData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="type" tick={{ fontSize: 12 }} />
                <YAxis allowDecimals={false} />
                <ChartTooltip
                  content={<ChartTooltipContent indicator="dot" />}
                />
                <Bar dataKey="count" name="count" radius={[4, 4, 0, 0]}>
                  {surfaceData.map((entry, index) => (
                    <Cell key={index} fill={surfaceConfig[entry.type].color} />
                  ))}
                </Bar>
              </BarChart>
            </ChartContainer>
          ) : (
            <p className="text-muted-foreground text-sm py-4 text-center">
              No surface data
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
