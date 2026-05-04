import type { MemoryNetworkNode } from '@/types'

export const MEMORY_CATEGORY_ORDER = [
  'DAILY',
  'PHILOSOPHICAL',
  'TECHNICAL',
  'FEELING',
  'RELATIONSHIP',
  'OBSERVATION',
  'CONVERSATION',
  'INTROSPECTION',
  'SELF_DISCOVERY',
  'DREAM',
  'LESSON',
] as const

export const MEMORY_CATEGORY_COLORS: Record<string, string> = {
  DAILY: 'hsl(210, 70%, 55%)',
  PHILOSOPHICAL: 'hsl(270, 60%, 55%)',
  TECHNICAL: 'hsl(145, 55%, 45%)',
  FEELING: 'hsl(0, 65%, 55%)',
  RELATIONSHIP: 'hsl(30, 70%, 55%)',
  OBSERVATION: 'hsl(185, 55%, 45%)',
  CONVERSATION: 'hsl(50, 65%, 50%)',
  INTROSPECTION: 'hsl(310, 55%, 50%)',
  SELF_DISCOVERY: 'hsl(240, 50%, 60%)',
  DREAM: 'hsl(160, 45%, 50%)',
  LESSON: 'hsl(90, 50%, 45%)',
  MEMORY: 'hsl(0, 0%, 60%)',
}

export const NOTION_TONE_COLORS = {
  positive: 'hsl(48, 82%, 55%)',
  negative: 'hsl(212, 62%, 50%)',
  neutral: 'hsl(172, 46%, 46%)',
} as const

export const CONVICTION_RING_COLOR = 'rgba(250, 204, 21, 0.95)'
export const SEARCH_HIGHLIGHT_COLOR = 'rgba(250, 204, 21, 0.65)'
export const NOTION_SOURCE_GRADIENT_END = 'hsla(45, 90%, 58%, 0.95)'

const POSITIVE_TONES = new Set([
  'joy',
  'excited',
  'moved',
  'grateful',
  'proud',
  'hopeful',
])

const NEGATIVE_TONES = new Set([
  'sad',
  'anxious',
  'frustrated',
  'angry',
  'lonely',
  'ashamed',
])

const extractLightness = (color: string) => {
  const match = color.match(/,\s*([0-9.]+)%\s*\)$/)
  return match ? Number(match[1]) : 50
}

export const notionToneGroup = (emotionTone?: string | null) => {
  const normalized = (emotionTone ?? '').toLowerCase()
  if (POSITIVE_TONES.has(normalized)) return 'positive'
  if (NEGATIVE_TONES.has(normalized)) return 'negative'
  return 'neutral'
}

export const getNodeFillColor = (node: MemoryNetworkNode) => {
  if (node.is_notion) {
    if (node.is_conviction) {
      return MEMORY_CATEGORY_COLORS.CONVERSATION
    }
    return NOTION_TONE_COLORS[notionToneGroup(node.emotion_tone)]
  }

  return (
    MEMORY_CATEGORY_COLORS[node.category.toUpperCase()] ??
    MEMORY_CATEGORY_COLORS.MEMORY
  )
}

export const getNodeTextColor = (fillColor: string) =>
  extractLightness(fillColor) >= 56 ? '#0f172a' : '#f8fafc'

export const getNodeBorderColor = (
  node: MemoryNetworkNode,
  fillColor: string,
) => {
  if (node.is_conviction) return CONVICTION_RING_COLOR
  return getNodeTextColor(fillColor) === '#0f172a'
    ? 'rgba(15, 23, 42, 0.42)'
    : 'rgba(248, 250, 252, 0.8)'
}

export const getEdgeStroke = (linkType: string) => {
  switch (linkType) {
    case 'caused_by':
      return 'hsl(0, 65%, 55%)'
    case 'leads_to':
      return 'hsl(145, 55%, 45%)'
    case 'notion_source':
      return 'hsl(270, 60%, 55%)'
    case 'notion_related':
      return 'hsl(45, 90%, 50%)'
    case 'meta_notion_link':
      return 'hsl(320, 60%, 55%)'
    default:
      return 'hsl(0, 0%, 60%)'
  }
}

export const getEdgeDashArray = (linkType: string) => {
  switch (linkType) {
    case 'related':
      return '4 4'
    case 'notion_related':
      return '6 4'
    case 'meta_notion_link':
      return '5 3'
    default:
      return undefined
  }
}

export const getEdgeStrokeWidth = (
  linkType: string,
  confidence = 0.3,
  highlighted = false,
) => {
  const emphasis = highlighted ? 1.5 : 0
  switch (linkType) {
    case 'similar':
      return confidence * 3 + 1 + emphasis
    case 'related':
      return 1 + emphasis
    case 'caused_by':
    case 'leads_to':
      return confidence * 4 + 1 + emphasis
    case 'notion_source':
      return 2 + emphasis
    case 'notion_related':
      return confidence * 3 + 1 + emphasis
    case 'meta_notion_link':
      return 2 + emphasis
    default:
      return Math.max(1.5, confidence * 3) + emphasis
  }
}

export const wasAccessedRecently = (lastAccessed?: string | null) => {
  if (!lastAccessed) return false
  const parsed = new Date(lastAccessed)
  if (Number.isNaN(parsed.valueOf())) return false
  return Date.now() - parsed.valueOf() <= 24 * 60 * 60 * 1000
}
