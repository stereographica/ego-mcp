type CircumplexChartProps = {
  valence: number | null | undefined
  arousal: number | null | undefined
  size?: number
}

const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value))

export const CircumplexChart = ({
  valence,
  arousal,
  size = 120,
}: CircumplexChartProps) => {
  const center = size / 2
  const radius = Math.max(8, center - 16)
  const hasPoint = valence != null && arousal != null
  const safeValence = clamp(valence ?? 0, -1, 1)
  const safeArousal = clamp(arousal ?? 0.5, 0, 1)
  const cx = center + safeValence * radius
  const cy = center - (safeArousal - 0.5) * 2 * radius

  return (
    <div
      data-testid="circumplex-chart"
      className="flex flex-col items-center gap-1"
    >
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
      >
        <title>Valence-arousal circumplex chart</title>
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke="var(--color-border)"
          strokeWidth="1.5"
        />
        <line
          x1={center - radius}
          y1={center}
          x2={center + radius}
          y2={center}
          stroke="var(--color-border)"
          strokeDasharray="4 4"
          strokeWidth="1"
        />
        <line
          x1={center}
          y1={center - radius}
          x2={center}
          y2={center + radius}
          stroke="var(--color-border)"
          strokeDasharray="4 4"
          strokeWidth="1"
        />
        <text
          x={center}
          y={12}
          textAnchor="middle"
          className="fill-muted-foreground text-[9px]"
        >
          aroused
        </text>
        <text
          x={center}
          y={size - 4}
          textAnchor="middle"
          className="fill-muted-foreground text-[9px]"
        >
          calm
        </text>
        <text
          x={6}
          y={center + 3}
          textAnchor="start"
          className="fill-muted-foreground text-[9px]"
        >
          unpleasant
        </text>
        <text
          x={size - 6}
          y={center + 3}
          textAnchor="end"
          className="fill-muted-foreground text-[9px]"
        >
          pleasant
        </text>
        {hasPoint ? (
          <circle
            data-testid="circumplex-dot"
            cx={cx}
            cy={cy}
            r="4"
            fill="var(--color-chart-2)"
          />
        ) : (
          <text
            data-testid="circumplex-na"
            x={center}
            y={center + 4}
            textAnchor="middle"
            className="fill-muted-foreground text-xs"
          >
            n/a
          </text>
        )}
      </svg>
      <p className="text-muted-foreground text-xs tabular-nums">
        {hasPoint
          ? `v: ${safeValence?.toFixed(2)} / a: ${safeArousal?.toFixed(2)}`
          : 'n/a'}
      </p>
    </div>
  )
}
