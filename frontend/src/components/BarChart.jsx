import PropTypes from 'prop-types'

function formatNumber(value) {
  const abs = Math.abs(value)
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`
  if (abs >= 1_000) return `${(value / 1_000).toFixed(1)}K`
  return `${Number(value).toFixed(2)}`
}

export default function BarChart({ data, xKey, yKey, title }) {
  if (!data?.length) {
    return <div className="card"><h3>{title}</h3><div className="empty-state">No data available.</div></div>
  }

  const maxValue = Math.max(...data.map((item) => Number(item[yKey]) || 0), 1)

  return (
    <div className="card">
      <h3>{title}</h3>
      <div className="bar-chart">
        {data.map((item) => {
          const width = `${(Number(item[yKey]) / maxValue) * 100}%`
          return (
            <div key={item[xKey]} className="bar-row">
              <div className="bar-label">{item[xKey]}</div>
              <div className="bar-track">
                <div className="bar-fill" style={{ width }} />
              </div>
              <div className="bar-value">{formatNumber(item[yKey])}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

BarChart.propTypes = {
  data: PropTypes.arrayOf(PropTypes.object),
  xKey: PropTypes.string.isRequired,
  yKey: PropTypes.string.isRequired,
  title: PropTypes.string.isRequired,
}
