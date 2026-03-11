/**
 * @file Unit tests for the DataTable component.
 * Verifies correct rendering of column headers, row data, and the
 * empty-state message when no rows are provided.
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import DataTable from '../components/DataTable'

describe('DataTable', () => {
  const columns = [
    { key: 'metric', label: 'Metric' },
    { key: 'value', label: 'Value' },
  ]

  it('renders column headers and row data', () => {
    const rows = [
      { metric: 'views', value: 100 },
      { metric: 'likes', value: 50 },
    ]
    render(<DataTable title="Stats" columns={columns} rows={rows} />)
    expect(screen.getByText('Stats')).toBeInTheDocument()
    expect(screen.getByText('Metric')).toBeInTheDocument()
    expect(screen.getByText('views')).toBeInTheDocument()
    expect(screen.getByText('50')).toBeInTheDocument()
  })

  it('renders empty row message when no rows', () => {
    render(<DataTable title="Empty" columns={columns} rows={[]} />)
    expect(screen.getByText('No rows available.')).toBeInTheDocument()
  })
})
