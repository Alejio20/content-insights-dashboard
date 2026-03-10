export function formatAxisValue(value) {
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(0)}K`
  return Number(value).toFixed(1)
}

export function niceSteps(min, max, count = 4) {
  if (max === min) return [min]
  const step = (max - min) / count
  return Array.from({ length: count + 1 }, (_, i) => min + step * i)
}
