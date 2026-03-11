/**
 * @file Unit tests for the MetricCard component.
 * Verifies that label, value, and optional hint text all render
 * correctly in the DOM.
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import MetricCard from '../components/MetricCard'

describe('MetricCard', () => {
  it('renders label, value, and hint', () => {
    render(<MetricCard label="Total Views" value="1,234" hint="Aggregate reach" />)
    expect(screen.getByText('Total Views')).toBeInTheDocument()
    expect(screen.getByText('1,234')).toBeInTheDocument()
    expect(screen.getByText('Aggregate reach')).toBeInTheDocument()
  })

  it('renders without hint', () => {
    render(<MetricCard label="Videos" value="50" />)
    expect(screen.getByText('Videos')).toBeInTheDocument()
    expect(screen.getByText('50')).toBeInTheDocument()
  })
})
