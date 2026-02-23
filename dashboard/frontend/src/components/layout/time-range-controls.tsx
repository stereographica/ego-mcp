import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import type { TimeRangePreset } from '@/types'

type TimeRangeControlsProps = {
  preset: TimeRangePreset
  onPresetChange: (value: TimeRangePreset) => void
  customFrom: string
  customTo: string
  onCustomFromChange: (value: string) => void
  onCustomToChange: (value: string) => void
}

const PRESETS: TimeRangePreset[] = ['15m', '1h', '6h', '24h', '7d', 'custom']

export const TimeRangeControls = ({
  preset,
  onPresetChange,
  customFrom,
  customTo,
  onCustomFromChange,
  onCustomToChange,
}: TimeRangeControlsProps) => (
  <div className="flex flex-wrap items-center gap-2">
    <ToggleGroup
      type="single"
      value={preset}
      onValueChange={(v) => {
        if (v) onPresetChange(v as TimeRangePreset)
      }}
      className="gap-1"
    >
      {PRESETS.map((key) => (
        <ToggleGroupItem key={key} value={key} size="sm">
          {key}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>

    {preset === 'custom' && (
      <>
        <input
          className="rounded-md border border-input bg-secondary px-2 py-1 text-sm"
          type="datetime-local"
          value={customFrom}
          onChange={(e) => onCustomFromChange(e.target.value)}
        />
        <input
          className="rounded-md border border-input bg-secondary px-2 py-1 text-sm"
          type="datetime-local"
          value={customTo}
          onChange={(e) => onCustomToChange(e.target.value)}
        />
      </>
    )}
  </div>
)
