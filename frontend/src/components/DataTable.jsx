/**
 * @file DataTable component.
 * Generic table that renders column headers and rows from dynamic
 * column/row definitions.  Falls back to an empty-state message
 * when no data is available.
 */

import PropTypes from 'prop-types'

export default function DataTable({ title, columns, rows }) {
  return (
    <div className="card table-card">
      <h3>{title}</h3>
      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.key}>{column.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows?.length ? (
              rows.map((row, index) => (
                <tr key={`${row.video_id ?? row.term ?? index}-${index}`}>
                  {columns.map((column) => (
                    <td key={column.key}>{row[column.key]}</td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={columns.length} className="empty-state">No rows available.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

DataTable.propTypes = {
  title: PropTypes.string.isRequired,
  columns: PropTypes.arrayOf(
    PropTypes.shape({
      key: PropTypes.string.isRequired,
      label: PropTypes.string.isRequired,
    })
  ).isRequired,
  rows: PropTypes.arrayOf(PropTypes.object),
}
