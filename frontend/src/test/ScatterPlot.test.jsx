/**
 * @file Unit tests for the ScatterPlot component.
 * Verifies SVG rendering with cluster data points and the empty-state
 * fallback when the points array is empty.
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ScatterPlot from '../components/ScatterPlot'

describe('ScatterPlot', () => {
  it('renders svg with points', () => {
    const points = [
      { video_id: 1, views: 1000, engagement_rate_pct: 5, cluster_id: 0, title: 'Test' },
      { video_id: 2, views: 2000, engagement_rate_pct: 3, cluster_id: 1, title: 'Test 2' },
    ]
    render(<ScatterPlot points={points} title="Cluster map" />)
    expect(screen.getByText('Cluster map')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Cluster map' })).toBeInTheDocument()
  })

  it('renders empty state when no points', () => {
    render(<ScatterPlot points={[]} title="Cluster map" />)
    expect(screen.getByText('No data available.')).toBeInTheDocument()
  })
})
