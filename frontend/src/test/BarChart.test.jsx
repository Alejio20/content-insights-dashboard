import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import BarChart from '../components/BarChart'

describe('BarChart', () => {
  it('renders bars for each data point', () => {
    const data = [
      { category: 'education', avg_views: 1000 },
      { category: 'entertainment', avg_views: 2000 },
    ]
    render(<BarChart data={data} xKey="category" yKey="avg_views" title="Views" />)
    expect(screen.getByText('education')).toBeInTheDocument()
    expect(screen.getByText('entertainment')).toBeInTheDocument()
    expect(screen.getByText('Views')).toBeInTheDocument()
  })

  it('renders empty state when data is null', () => {
    render(<BarChart data={null} xKey="category" yKey="avg_views" title="Views" />)
    expect(screen.getByText('No data available.')).toBeInTheDocument()
  })

  it('renders empty state when data is empty', () => {
    render(<BarChart data={[]} xKey="category" yKey="avg_views" title="Views" />)
    expect(screen.getByText('No data available.')).toBeInTheDocument()
  })
})
