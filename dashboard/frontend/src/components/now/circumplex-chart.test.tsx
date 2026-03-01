import { render, screen } from '@testing-library/react'

import { CircumplexChart } from '@/components/now/circumplex-chart'

describe('CircumplexChart', () => {
  it('renders dot when valence/arousal are provided', () => {
    render(<CircumplexChart valence={0.5} arousal={0.8} />)

    expect(screen.getByTestId('circumplex-dot')).toBeInTheDocument()
    expect(screen.getByText(/v: 0.50/i)).toBeInTheDocument()
    expect(screen.getByText(/a: 0.80/i)).toBeInTheDocument()
  })

  it('renders n/a when valence/arousal are null', () => {
    render(<CircumplexChart valence={null} arousal={null} />)

    expect(screen.getByTestId('circumplex-na')).toBeInTheDocument()
    expect(screen.queryByTestId('circumplex-dot')).not.toBeInTheDocument()
  })

  it('renders n/a when valence/arousal are undefined', () => {
    render(<CircumplexChart valence={undefined} arousal={undefined} />)

    expect(screen.getByTestId('circumplex-na')).toBeInTheDocument()
    expect(screen.queryByTestId('circumplex-dot')).not.toBeInTheDocument()
  })

  it('supports boundary values', () => {
    const { rerender } = render(
      <CircumplexChart valence={-1.0} arousal={0.0} />,
    )
    expect(screen.getByTestId('circumplex-dot')).toBeInTheDocument()

    rerender(<CircumplexChart valence={1.0} arousal={1.0} />)
    expect(screen.getByTestId('circumplex-dot')).toBeInTheDocument()
  })
})
