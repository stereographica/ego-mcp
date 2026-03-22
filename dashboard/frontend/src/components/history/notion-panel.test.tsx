import { render, screen } from '@testing-library/react'

import { NotionPanel } from '@/components/history/notion-panel'

describe('NotionPanel', () => {
  it('renders notion confidence rows', () => {
    render(
      <NotionPanel
        notions={[
          {
            id: 'notion-1',
            label: 'Pattern seeking',
            emotion_tone: 'curious',
            confidence: 0.82,
            source_count: 3,
            source_memory_ids: ['mem-1'],
            created: '2026-01-01T11:00:00Z',
            last_reinforced: '2026-01-01T12:00:00Z',
          },
        ]}
      />,
    )

    expect(screen.getByText('Notions')).toBeInTheDocument()
    expect(screen.getByText('Pattern seeking')).toBeInTheDocument()
    expect(screen.getByText('82%')).toBeInTheDocument()
  })
})
