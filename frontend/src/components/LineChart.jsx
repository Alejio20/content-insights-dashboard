/**
 * @file LineChart component.
 * Renders a responsive SVG time-series line chart with hover tooltips,
 * evenly-spaced grid lines, and automatic axis labelling.  Uses the
 * shared chartUtils helpers for value formatting and grid-step calculation.
 */

import { useCallback, useRef, useState } from 'react'
import PropTypes from 'prop-types'
import { formatAxisValue, niceSteps } from './chartUtils'

export default function LineChart({ data, xKey, yKey, title }) {
  const [tooltip, setTooltip] = useState(null)
  const containerRef = useRef(null)

  const showTooltip = useCallback((e, point) => {
    const rect = containerRef.current.getBoundingClientRect()
    setTooltip({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top - 10,
      text: `${point.label}: ${Number(point.y).toLocaleString(undefined, { maximumFractionDigits: 2 })}`,
    })
  }, [])

  const hideTooltip = useCallback(() => setTooltip(null), [])

  if (!data?.length) {
    return <div className="card"><h3>{title}</h3><div className="empty-state">No data available.</div></div>
  }

  const width = 720
  const height = 280
  const padLeft = 60
  const padRight = 20
  const padTop = 16
  const padBottom = 40
  const plotW = width - padLeft - padRight
  const plotH = height - padTop - padBottom

  const points = data.map((item, index) => ({ label: item[xKey], x: index, y: Number(item[yKey]) }))
  const yValues = points.map((p) => p.y)
  const minY = Math.min(...yValues)
  const maxY = Math.max(...yValues)

  const mapX = (index) => padLeft + (index / Math.max(points.length - 1, 1)) * plotW
  const mapY = (value) => {
    if (maxY === minY) return padTop + plotH / 2
    return padTop + plotH - ((value - minY) / (maxY - minY)) * plotH
  }

  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${mapX(p.x)} ${mapY(p.y)}`).join(' ')
  const gridSteps = niceSteps(minY, maxY, 4)

  return (
    <div className="card chart-container" ref={containerRef}>
      <h3>{title}</h3>
      <svg viewBox={`0 0 ${width} ${height}`} className="line-chart" role="img" aria-label={title}>
        {gridSteps.map((v) => (
          <g key={v}>
            <line x1={padLeft} x2={width - padRight} y1={mapY(v)} y2={mapY(v)} className="grid-line" />
            <text x={padLeft - 8} y={mapY(v) + 4} className="axis-label" textAnchor="end">{formatAxisValue(v)}</text>
          </g>
        ))}
        <path d={path} fill="none" strokeWidth="3" className="line-path" />
        {points.map((point, index) => {
          const cx = mapX(index)
          const cy = mapY(point.y)
          const showLabel = index % Math.ceil(points.length / 6) === 0 || index === points.length - 1
          return (
            <g key={`${point.label}-${index}`}>
              <circle
                cx={cx}
                cy={cy}
                r="5"
                className="line-point"
                onMouseMove={(e) => showTooltip(e, point)}
                onMouseLeave={hideTooltip}
                style={{ cursor: 'pointer' }}
              />
              {showLabel ? (
                <text x={cx} y={height - 8} className="axis-label" textAnchor="middle">{point.label}</text>
              ) : null}
            </g>
          )
        })}
      </svg>
      {tooltip ? (
        <div className="chart-tooltip" style={{ left: tooltip.x, top: tooltip.y }}>
          {tooltip.text}
        </div>
      ) : null}
    </div>
  )
}

LineChart.propTypes = {
  data: PropTypes.arrayOf(PropTypes.object),
  xKey: PropTypes.string.isRequired,
  yKey: PropTypes.string.isRequired,
  title: PropTypes.string.isRequired,
}
