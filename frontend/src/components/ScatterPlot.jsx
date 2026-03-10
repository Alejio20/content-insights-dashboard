import { useCallback, useRef, useState } from 'react'
import PropTypes from 'prop-types'
import { formatAxisValue, niceSteps } from './chartUtils'

const clusterClass = ['cluster-a', 'cluster-b', 'cluster-c', 'cluster-d', 'cluster-e', 'cluster-f']

export default function ScatterPlot({ points, title }) {
  const [tooltip, setTooltip] = useState(null)
  const containerRef = useRef(null)

  const showTooltip = useCallback((e, point) => {
    const rect = containerRef.current.getBoundingClientRect()
    setTooltip({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top - 10,
      text: `${point.title}\nViews: ${Number(point.views).toLocaleString()}\nEngagement: ${point.engagement_rate_pct}%\nCluster: ${point.cluster_id}`,
    })
  }, [])

  const hideTooltip = useCallback(() => setTooltip(null), [])

  if (!points?.length) {
    return <div className="card"><h3>{title}</h3><div className="empty-state">No data available.</div></div>
  }

  const width = 720
  const height = 340
  const padLeft = 60
  const padRight = 20
  const padTop = 16
  const padBottom = 40
  const plotW = width - padLeft - padRight
  const plotH = height - padTop - padBottom

  const xValues = points.map((p) => Number(p.views))
  const yValues = points.map((p) => Number(p.engagement_rate_pct))
  const minX = Math.min(...xValues)
  const maxX = Math.max(...xValues)
  const minY = Math.min(...yValues)
  const maxY = Math.max(...yValues)

  const mapX = (value) => padLeft + ((value - minX) / Math.max(maxX - minX, 1)) * plotW
  const mapY = (value) => padTop + plotH - ((value - minY) / Math.max(maxY - minY, 1)) * plotH

  const xSteps = niceSteps(minX, maxX, 4)
  const ySteps = niceSteps(minY, maxY, 4)

  return (
    <div className="card chart-container" ref={containerRef}>
      <h3>{title}</h3>
      <svg viewBox={`0 0 ${width} ${height}`} className="scatter-chart" role="img" aria-label={title}>
        {ySteps.map((v) => (
          <g key={`y-${v}`}>
            <line x1={padLeft} x2={width - padRight} y1={mapY(v)} y2={mapY(v)} className="grid-line" />
            <text x={padLeft - 8} y={mapY(v) + 4} className="axis-label" textAnchor="end">{formatAxisValue(v)}</text>
          </g>
        ))}
        {xSteps.map((v) => (
          <text key={`x-${v}`} x={mapX(v)} y={height - 8} className="axis-label" textAnchor="middle">{formatAxisValue(v)}</text>
        ))}
        {points.map((point) => (
          <circle
            key={`${point.video_id}-${point.cluster_id}`}
            cx={mapX(Number(point.views))}
            cy={mapY(Number(point.engagement_rate_pct))}
            r="5"
            className={clusterClass[Number(point.cluster_id) % clusterClass.length]}
            onMouseMove={(e) => showTooltip(e, point)}
            onMouseLeave={hideTooltip}
            style={{ cursor: 'pointer' }}
          />
        ))}
      </svg>
      <div className="scatter-legend">X: views &middot; Y: engagement rate %</div>
      {tooltip ? (
        <div className="chart-tooltip chart-tooltip-multi" style={{ left: tooltip.x, top: tooltip.y }}>
          {tooltip.text.split('\n').map((line, i) => <div key={i}>{line}</div>)}
        </div>
      ) : null}
    </div>
  )
}

ScatterPlot.propTypes = {
  points: PropTypes.arrayOf(PropTypes.object),
  title: PropTypes.string.isRequired,
}
