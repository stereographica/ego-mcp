import { CircumplexChart } from '@/components/now/circumplex-chart'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { CurrentResponse } from '@/types'

type CircumplexCardProps = {
  current: CurrentResponse | null
}

export const CircumplexCard = ({ current }: CircumplexCardProps) => {
  const valence =
    current?.latest_emotion?.valence ??
    current?.latest?.numeric_metrics?.valence
  const arousal =
    current?.latest_emotion?.arousal ??
    current?.latest?.numeric_metrics?.arousal

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Valence-Arousal</CardTitle>
      </CardHeader>
      <CardContent className="flex justify-center">
        <CircumplexChart valence={valence} arousal={arousal} size={200} />
      </CardContent>
    </Card>
  )
}
