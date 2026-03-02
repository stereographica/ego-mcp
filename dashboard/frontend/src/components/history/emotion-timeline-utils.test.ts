import {
  buildEmotionAxis,
  emotionLabelForPoint,
} from '@/components/history/emotion-timeline-utils'
import type { EmotionTrendPoint } from '@/types'

describe('buildEmotionAxis', () => {
  it('keeps neutral at center and includes the full known emotion set', () => {
    const points: EmotionTrendPoint[] = [
      { ts: '2026-01-01T12:00:00Z', value: 0.3, emotion_primary: 'curious' },
      { ts: '2026-01-01T12:01:00Z', value: 0.7, emotion_primary: 'happy' },
      { ts: '2026-01-01T12:02:00Z', value: -0.6, emotion_primary: 'sad' },
      { ts: '2026-01-01T12:03:00Z', value: -0.8, emotion_primary: 'anxious' },
    ]

    const axis = buildEmotionAxis(points)

    expect(axis.emotionToLevel.get('neutral')).toBe(0)
    expect(axis.emotionToLevel.get('happy')).toBeGreaterThan(0)
    expect(axis.emotionToLevel.get('curious')).toBeGreaterThan(0)
    expect(axis.emotionToLevel.get('sad')).toBeLessThan(0)
    expect(axis.emotionToLevel.get('anxious')).toBeLessThan(0)
    expect(axis.emotionToLevel.get('surprised')).toBeGreaterThan(0)
    expect(axis.emotionToLevel.get('melancholy')).toBeLessThan(0)
    expect(axis.ticks).toContain(0)
    expect(axis.ticks.length).toBe(axis.emotionToLevel.size)
    expect(axis.ticks.length).toBeGreaterThanOrEqual(30)
  })

  it('adds unknown observed emotions to the fixed legend', () => {
    const points: EmotionTrendPoint[] = [
      { ts: '2026-01-01T12:10:00Z', value: 0.6, emotion_primary: 'euphoric' },
      { ts: '2026-01-01T12:11:00Z', value: -0.7, emotion_primary: 'gloomy' },
    ]

    const axis = buildEmotionAxis(points)

    expect(axis.emotionToLevel.get('euphoric')).toBeGreaterThan(0)
    expect(axis.emotionToLevel.get('gloomy')).toBeLessThan(0)
  })

  it('returns emotion label for tooltip from primary emotion first', () => {
    const levelToEmotion = new Map<number, string>([
      [-1, 'sad'],
      [0, 'neutral'],
      [1, 'happy'],
    ])

    expect(
      emotionLabelForPoint(
        { emotion_primary: 'Curious', emotion_level: -1 },
        levelToEmotion,
      ),
    ).toBe('curious')
    expect(emotionLabelForPoint({ emotion_level: 1 }, levelToEmotion)).toBe(
      'happy',
    )
    expect(emotionLabelForPoint(undefined, levelToEmotion)).toBe('unknown')
  })
})
