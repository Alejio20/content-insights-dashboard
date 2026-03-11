/**
 * @file useDashboardData custom hook.
 * Centralises all API communication, filter state, WebSocket real-time
 * refresh logic, and CSV upload handling for the dashboard.  Returns
 * every piece of data and every handler the App component needs.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

/** Backend API root -- overridable via VITE_API_BASE_URL env variable. */
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
/** Derived WebSocket URL (http → ws, https → wss). */
const WS_BASE = API_BASE.replace(/^http/, 'ws')

/**
 * Serialise the active filter state into a URL query string.
 * Omits "all" category and empty date fields to keep URLs clean.
 */
function buildQuery(filters) {
  const params = new URLSearchParams()
  if (filters.category && filters.category !== 'all') params.set('category', filters.category)
  if (filters.start_date) params.set('start_date', filters.start_date)
  if (filters.end_date) params.set('end_date', filters.end_date)
  return params.toString()
}

/**
 * Generic JSON fetcher with automatic filter-to-query-string conversion.
 * Throws on non-2xx responses, preferring the server's `detail` message.
 */
async function fetchJson(path, filters) {
  const query = filters ? buildQuery(filters) : ''
  const url = `${API_BASE}${path}${query ? `?${query}` : ''}`
  const response = await fetch(url)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail || `Request failed: ${response.status}`)
  }
  return response.json()
}

export { API_BASE, buildQuery }

export default function useDashboardData() {
  const [options, setOptions] = useState(null)
  const [filters, setFilters] = useState({ category: 'all', start_date: '', end_date: '' })
  const [summary, setSummary] = useState(null)
  const [trends, setTrends] = useState(null)
  const [clusters, setClusters] = useState(null)
  const [anomalies, setAnomalies] = useState(null)
  const [videos, setVideos] = useState([])
  const [selectedVideoId, setSelectedVideoId] = useState('')
  const [similar, setSimilar] = useState(null)
  const [validation, setValidation] = useState(null)
  const [clusterExperiment, setClusterExperiment] = useState(null)
  const [anomalyExperiment, setAnomalyExperiment] = useState(null)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')

  const refreshCounter = useRef(0)
  const wsRef = useRef(null)

  // WebSocket: listen for server-side data-refresh events (e.g. after CSV upload).
  useEffect(() => {
    let ws
    try {
      ws = new WebSocket(`${WS_BASE}/ws`)
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data)
        if (msg.type === 'data_refreshed') {
          refreshCounter.current += 1
          setLoading(true)
          // Shallow-clone options to trigger the data-fetch effect below.
          setOptions((prev) => prev ? { ...prev } : prev)
        }
      }
      ws.onerror = () => {}
      wsRef.current = ws
    } catch { /* WebSocket is optional -- dashboard still works via polling */ }
    return () => { if (ws) ws.close() }
  }, [])

  // On mount: fetch available filter options and seed the date range.
  useEffect(() => {
    let active = true
    fetchJson('/filters')
      .then((payload) => {
        if (!active) return
        setOptions(payload)
        setLoading(true)
        setFilters((current) => ({
          ...current,
          start_date: payload.date_range.min,
          end_date: payload.date_range.max,
        }))
      })
      .catch((err) => {
        if (active) setError(err.message)
      })
    return () => { active = false }
  }, [])

  // Whenever options or filters change, fetch all dashboard data in parallel.
  useEffect(() => {
    if (!options) return
    let active = true

    Promise.all([
      fetchJson('/validation'),
      fetchJson('/dashboard/summary', filters),
      fetchJson('/analysis/trends', filters),
      fetchJson('/analysis/clusters', filters),
      fetchJson('/analysis/anomalies', filters),
      fetchJson('/videos', filters),
      fetchJson('/experiments/clusters', filters),
      fetchJson('/experiments/anomalies', filters),
    ])
      .then(([valP, sumP, trendP, clustP, anomP, vidP, clustExpP, anomExpP]) => {
        if (!active) return
        setValidation(valP)
        setSummary(sumP)
        setTrends(trendP)
        setClusters(clustP)
        setAnomalies(anomP)
        setVideos(vidP.items || [])
        setClusterExperiment(clustExpP)
        setAnomalyExperiment(anomExpP)
        setSelectedVideoId((current) => current || String(vidP.items?.[0]?.video_id || ''))
      })
      .catch((err) => {
        if (active) setError(err.message)
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    // `active` flag prevents state updates if the component unmounts mid-flight.
    return () => { active = false }
  }, [options, filters])

  // Fetch title-similar videos whenever the selected anchor video changes.
  useEffect(() => {
    if (!selectedVideoId) return
    let active = true
    fetchJson(`/analysis/similar/${selectedVideoId}`)
      .then((payload) => {
        if (active) setSimilar(payload)
      })
      .catch((err) => {
        if (active) setError(err.message)
      })
    return () => { active = false }
  }, [selectedVideoId])

  /** Update a single filter field by input name and trigger a data reload. */
  const handleFilterChange = useCallback((event) => {
    const { name, value } = event.target
    setLoading(true)
    setError('')
    setFilters((current) => ({ ...current, [name]: value }))
  }, [])

  /** Upload a CSV file to the backend, refresh filters, and reload data. */
  const uploadCsv = useCallback(async (file) => {
    setUploading(true)
    setError('')
    try {
      const form = new FormData()
      form.append('file', file)
      const resp = await fetch(`${API_BASE}/upload`, { method: 'POST', body: form })
      if (!resp.ok) {
        const body = await resp.json().catch(() => null)
        throw new Error(body?.detail || `Upload failed: ${resp.status}`)
      }
      const data = await resp.json()
      setValidation(data.validation)
      setLoading(true)
      const newFilters = await fetchJson('/filters')
      setOptions(newFilters)
      setFilters((c) => ({ ...c, start_date: newFilters.date_range.min, end_date: newFilters.date_range.max }))
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
    }
  }, [])

  const clearError = useCallback(() => setError(''), [])

  return {
    options,
    filters,
    summary,
    trends,
    clusters,
    anomalies,
    videos,
    selectedVideoId,
    setSelectedVideoId,
    similar,
    validation,
    clusterExperiment,
    anomalyExperiment,
    loading,
    uploading,
    error,
    handleFilterChange,
    uploadCsv,
    clearError,
  }
}
