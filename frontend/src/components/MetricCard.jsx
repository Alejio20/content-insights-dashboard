/**
 * @file MetricCard component.
 * Displays a single KPI value with a label and optional explanatory
 * hint text.  Used in the overview grid at the top of the dashboard.
 */

import PropTypes from 'prop-types'

export default function MetricCard({ label, value, hint }) {
  return (
    <div className="card metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {hint ? <div className="metric-hint">{hint}</div> : null}
    </div>
  )
}

MetricCard.propTypes = {
  label: PropTypes.string.isRequired,
  value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]).isRequired,
  hint: PropTypes.string,
}
