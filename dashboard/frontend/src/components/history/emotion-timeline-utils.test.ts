import { buildEmotionAxis } from '@/components/history/emotion-timeline-utils'
import type { EmotionTrendPoint } from '@/types'

describe('buildEmotionAxis', () => {
  it('keeps neutral at center and arranges positive/negative emotions around it', () => {
    const points: EmotionTrendPoint[] = [
      { ts: '2026-01-01T12:00:00Z', value: 0.3, emotion_primary: 'curious' },
      { ts: '2026-01-01T12:01:00Z', value: 0.7, emotion_primary: 'happy' },
      { ts: '2026-01-01T12:02:00Z', value: -0.6, emotion_primary: 'sad' },
      { ts: '2026-01-01T12:03:00Z', value: -0.8, emotion_primary: 'anxious' },
    ]

    const axis = buildEmotionAxis(points)

    expect(axis.emotionToLevel.get('neutral')).toBe(0)
    expect(axis.emotionToLevel.get('curious')).toBe(1)
    expect(axis.emotionToLevel.get('happy')).toBe(2)
    expect(axis.emotionToLevel.get('sad')).toBe(-1)
    expect(axis.emotionToLevel.get('anxious')).toBe(-2)
    expect(axis.ticks).toEqual([-2, -1, 0, 1, 2])
  })
})
