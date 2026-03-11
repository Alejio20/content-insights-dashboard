/**
 * @file Shared chart utility functions.
 * Provides axis-label formatting and grid-step calculation used by
 * LineChart and ScatterPlot SVG visualisations.
 */

/**
 * Abbreviate a numeric axis value to K/M notation for compact labels.
 * @param {number} value - The raw numeric value.
 * @returns {string} Human-readable abbreviated string.
 */
export function formatAxisValue(value) {
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(0)}K`
  return Number(value).toFixed(1)
}

/**
 * Generate evenly-spaced grid-line values between min and max.
 * @param {number} min   - Lower bound of the data range.
 * @param {number} max   - Upper bound of the data range.
 * @param {number} count - Desired number of intervals (grid lines = count + 1).
 * @returns {number[]} Array of tick values from min to max inclusive.
 */
export function niceSteps(min, max, count = 4) {
  if (max === min) return [min]
  const step = (max - min) / count
  return Array.from({ length: count + 1 }, (_, i) => min + step * i)
}
