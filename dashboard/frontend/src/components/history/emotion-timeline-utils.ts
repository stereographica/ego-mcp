import type { EmotionTrendPoint } from '@/types'

type EmotionStat = {
  sum: number
  count: number
}

export type EmotionAxis = {
  emotionToLevel: Map<string, number>
  levelToEmotion: Map<number, string>
  ticks: number[]
}

const FALLBACK_EMOTION_VALENCE: Record<string, number> = {
  happy: 0.6,
  excited: 0.7,
  calm: 0.3,
  neutral: 0,
  curious: 0.3,
  contemplative: 0.1,
  thoughtful: 0.1,
  grateful: 0.7,
  vulnerable: -0.3,
  content: 0.5,
  fulfilled: 0.6,
  touched: 0.5,
  moved: 0.5,
  concerned: -0.3,
  hopeful: 0.4,
  peaceful: 0.4,
  love: 0.8,
  warm: 0.5,
  sad: -0.6,
  anxious: -0.6,
  angry: -0.7,
  frustrated: -0.5,
  lonely: -0.6,
  afraid: -0.8,
  ashamed: -0.7,
  bored: -0.3,
  nostalgic: 0.1,
  contentment: 0.5,
  melancholy: -0.4,
  surprised: 0.1,
}

export const normalizeEmotion = (value: string) => value.trim().toLowerCase()

const valenceFor = (emotion: string, observed: number | undefined) => {
  if (Number.isFinite(observed)) return observed as number
  return FALLBACK_EMOTION_VALENCE[emotion] ?? 0
}

export const buildEmotionAxis = (points: EmotionTrendPoint[]): EmotionAxis => {
  const stats = new Map<string, EmotionStat>()

  for (const point of points) {
    if (typeof point.emotion_primary !== 'string') continue
    const emotion = normalizeEmotion(point.emotion_primary)
    if (emotion.length === 0) continue

    const current = stats.get(emotion) ?? { sum: 0, count: 0 }
    current.sum += valenceFor(emotion, point.value)
    current.count += 1
    stats.set(emotion, current)
  }

  stats.set('neutral', stats.get('neutral') ?? { sum: 0, count: 1 })

  const positives: Array<{ emotion: string; score: number }> = []
  const negatives: Array<{ emotion: string; score: number }> = []

  for (const [emotion, stat] of stats) {
    if (emotion === 'neutral') continue
    const score =
      stat.count > 0
        ? stat.sum / stat.count
        : (FALLBACK_EMOTION_VALENCE[emotion] ?? 0)
    if (score >= 0) {
      positives.push({ emotion, score })
      continue
    }
    negatives.push({ emotion, score })
  }

  positives.sort(
    (lhs, rhs) =>
      lhs.score - rhs.score || lhs.emotion.localeCompare(rhs.emotion),
  )
  negatives.sort(
    (lhs, rhs) =>
      rhs.score - lhs.score || lhs.emotion.localeCompare(rhs.emotion),
  )

  const emotionToLevel = new Map<string, number>()
  emotionToLevel.set('neutral', 0)

  positives.forEach((entry, index) => {
    emotionToLevel.set(entry.emotion, index + 1)
  })

  negatives.forEach((entry, index) => {
    emotionToLevel.set(entry.emotion, -(index + 1))
  })

  const levelToEmotion = new Map<number, string>()
  for (const [emotion, level] of emotionToLevel) {
    levelToEmotion.set(level, emotion)
  }

  const ticks = Array.from(levelToEmotion.keys()).sort((lhs, rhs) => lhs - rhs)

  return { emotionToLevel, levelToEmotion, ticks }
}
