/**
 * @file Root dashboard component.
 * Orchestrates the full dashboard layout: KPI cards, bar/line charts,
 * scatter plots, cluster narratives, trend tables, experiment results,
 * A/B test controls, anomaly lists, and content-similarity search.
 * All data flows through the useDashboardData hook.
 */

import { useCallback, useMemo, useRef, useState } from 'react'
import PropTypes from 'prop-types'
import MetricCard from './components/MetricCard'
import BarChart from './components/BarChart'
import LineChart from './components/LineChart'
import ScatterPlot from './components/ScatterPlot'
import DataTable from './components/DataTable'
import useDashboardData, { API_BASE, buildQuery } from './hooks/useDashboardData'

/** Format a number with locale-aware thousand separators. */
function formatInteger(value) {
  return Number(value).toLocaleString()
}

/** Format a number to a fixed number of decimal places. */
function formatFloat(value, digits = 2) {
  return Number(value).toFixed(digits)
}

/* ── Upload ───────────────────────────────────────────────────── */

/** Hidden file-input wrapper that triggers CSV upload on file selection. */
function UploadSection({ onUpload, uploading }) {
  const inputRef = useRef(null)

  const handleChange = useCallback((e) => {
    const file = e.target.files?.[0]
    if (file) onUpload(file)
    e.target.value = ''
  }, [onUpload])

  return (
    <div className="upload-section">
      <input ref={inputRef} type="file" accept=".csv" onChange={handleChange} hidden />
      <button className="btn btn-secondary" onClick={() => inputRef.current?.click()} disabled={uploading}>
        {uploading ? 'Uploading\u2026' : 'Upload CSV'}
      </button>
    </div>
  )
}

UploadSection.propTypes = {
  onUpload: PropTypes.func.isRequired,
  uploading: PropTypes.bool,
}

/* ── Download buttons ─────────────────────────────────────────── */

/** Anchor links that trigger server-side CSV and PDF report downloads. */
function DownloadButtons({ filters }) {
  const query = buildQuery(filters)
  const qs = query ? `?${query}` : ''
  return (
    <div className="download-buttons">
      <a className="btn btn-secondary" href={`${API_BASE}/reports/csv${qs}`} download>Download CSV</a>
      <a className="btn btn-secondary" href={`${API_BASE}/reports/pdf${qs}`} download>Download PDF</a>
    </div>
  )
}

DownloadButtons.propTypes = {
  filters: PropTypes.object.isRequired,
}

/* ── Overview ─────────────────────────────────────────────────── */

/** Grid of KPI MetricCards (videos, views, engagement, watch time). */
function OverviewSection({ summary }) {
  const cards = useMemo(() => {
    if (!summary?.totals) return []
    return [
      { label: 'Videos', value: formatInteger(summary.totals.videos), hint: 'Rows after filtering' },
      { label: 'Total Views', value: formatInteger(summary.totals.total_views), hint: 'Aggregate reach' },
      { label: 'Avg Engagement', value: `${formatFloat(summary.totals.avg_engagement_rate_pct, 2)}%`, hint: 'Likes + comments + shares per view' },
      { label: 'Avg Watch Time', value: `${formatFloat(summary.totals.avg_watch_time_seconds, 1)} sec`, hint: 'Watch time per view' },
    ]
  }, [summary])

  return (
    <section className="metric-grid">
      {cards.map((card) => (
        <MetricCard key={card.label} label={card.label} value={card.value} hint={card.hint} />
      ))}
    </section>
  )
}

OverviewSection.propTypes = {
  summary: PropTypes.shape({ totals: PropTypes.object }),
}

/* ── Charts ───────────────────────────────────────────────────── */

/** Category/thumbnail bar charts, monthly line charts, weekday + rolling trend visuals. */
function ChartsSection({ summary, trends }) {
  return (
    <>
      <section className="two-column-grid">
        <BarChart data={summary.by_category} xKey="category" yKey="avg_views" title="Average views by category" />
        <BarChart data={summary.by_thumbnail_style} xKey="thumbnail_style" yKey="avg_engagement_rate_pct" title="Average engagement by thumbnail style" />
      </section>
      <section className="two-column-grid">
        <LineChart data={summary.monthly} xKey="publish_month" yKey="avg_views" title="Monthly average views" />
        <LineChart data={summary.monthly} xKey="publish_month" yKey="avg_engagement_rate_pct" title="Monthly average engagement" />
      </section>
      {trends?.weekday_lift ? (
        <section className="two-column-grid">
          <BarChart data={trends.weekday_lift} xKey="publish_weekday" yKey="avg_watch_time_seconds" title="Avg watch time by weekday" />
          {trends.rolling_trends ? (
            <LineChart data={trends.rolling_trends} xKey="publish_date" yKey="rolling_views_30d" title="30-day rolling average views" />
          ) : <div className="card empty-state">No rolling data available.</div>}
        </section>
      ) : null}
    </>
  )
}

ChartsSection.propTypes = {
  summary: PropTypes.shape({
    by_category: PropTypes.array,
    by_thumbnail_style: PropTypes.array,
    monthly: PropTypes.array,
  }),
  trends: PropTypes.shape({
    weekday_lift: PropTypes.array,
    rolling_trends: PropTypes.array,
  }),
}

/* ── Clusters ─────────────────────────────────────────────────── */

/** Scatter plot of cluster assignments paired with a narrative summary per cluster. */
function ClusterSection({ clusters }) {
  return (
    <section className="two-column-grid">
      <ScatterPlot points={clusters?.points || []} title={`Cluster map (${clusters?.best_k || '-'} groups)`} />
      <div className="card">
        <h3>Cluster narratives</h3>
        <div className="cluster-list">
          {(clusters?.clusters || []).map((cluster) => (
            <div key={cluster.cluster_id} className="cluster-item">
              <div className="cluster-title">Cluster {cluster.cluster_id} &middot; {cluster.label}</div>
              <div>{formatInteger(cluster.videos)} videos</div>
              <div>{formatInteger(cluster.avg_views)} avg views</div>
              <div>{formatFloat(cluster.avg_engagement_rate_pct, 2)}% avg engagement</div>
              <div>{formatFloat(cluster.avg_watch_time_seconds, 1)} sec avg watch time</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

ClusterSection.propTypes = {
  clusters: PropTypes.shape({ points: PropTypes.array, best_k: PropTypes.number, clusters: PropTypes.array }),
}

/* ── Trends ───────────────────────────────────────────────────── */

/** Correlation table, title-token lift table, and metadata signal R-squared card. */
function TrendsSection({ trends }) {
  return (
    <section className="three-column-grid trends-grid">
      <DataTable
        title="Correlation to views"
        columns={[
          { key: 'metric', label: 'Metric' },
          { key: 'correlation', label: 'Correlation' },
        ]}
        rows={trends?.correlations_to_views || []}
      />
      <DataTable
        title="Title token lift"
        columns={[
          { key: 'term', label: 'Term' },
          { key: 'lift', label: 'Lift' },
        ]}
        rows={trends?.title_token_lift || []}
      />
      <div className="card insight-card trends-insight-card">
        <h3>Metadata signal</h3>
        <div className="big-number">R&sup2; {formatFloat(trends?.metadata_signal?.cross_validated_r2 || 0, 3)}</div>
        <p>{trends?.metadata_signal?.interpretation}</p>
        <ul>
          {(trends?.metadata_signal?.top_features || []).slice(0, 6).map((feature) => (
            <li key={feature.feature}>{feature.feature}: {feature.coefficient}</li>
          ))}
        </ul>
      </div>
    </section>
  )
}

TrendsSection.propTypes = {
  trends: PropTypes.shape({
    correlations_to_views: PropTypes.array,
    title_token_lift: PropTypes.array,
    metadata_signal: PropTypes.shape({
      cross_validated_r2: PropTypes.number,
      interpretation: PropTypes.string,
      top_features: PropTypes.array,
    }),
  }),
}

/* ── Experiments ──────────────────────────────────────────────── */

/** Side-by-side tables showing cluster k-sweep and anomaly contamination-sweep results. */
function ExperimentSection({ clusterExperiment, anomalyExperiment }) {
  if (!clusterExperiment?.runs && !anomalyExperiment?.runs) return null

  return (
    <section className="two-column-grid">
      <DataTable
        title="Cluster experiment (k comparison)"
        columns={[
          { key: 'k', label: 'k' },
          { key: 'silhouette_score', label: 'Silhouette' },
          { key: 'inertia', label: 'Inertia' },
        ]}
        rows={clusterExperiment?.runs || []}
      />
      <DataTable
        title="Anomaly experiment (contamination)"
        columns={[
          { key: 'contamination', label: 'Rate' },
          { key: 'anomalies_found', label: 'Flagged' },
          { key: 'pct_flagged', label: '% Flagged' },
          { key: 'mean_anomaly_score', label: 'Avg Anomaly Score' },
        ]}
        rows={anomalyExperiment?.runs || []}
      />
    </section>
  )
}

ExperimentSection.propTypes = {
  clusterExperiment: PropTypes.shape({ runs: PropTypes.array }),
  anomalyExperiment: PropTypes.shape({ runs: PropTypes.array }),
}

/* ── A/B Test ────────────────────────────────────────────────── */

/** Dropdown options for the metric selector in the A/B test panel. */
const AB_METRICS = [
  { value: 'views', label: 'Views' },
  { value: 'engagement_rate_pct', label: 'Engagement %' },
  { value: 'avg_watch_time_seconds', label: 'Avg Watch Time' },
  { value: 'like_rate', label: 'Like Rate' },
  { value: 'comment_rate', label: 'Comment Rate' },
  { value: 'share_rate', label: 'Share Rate' },
]

/** Interactive A/B test panel: choose attribute or title-keyword mode, pick variants, and run a Welch's t-test. */
function ABTestSection({ options, filters }) {
  const [mode, setMode] = useState('attribute')
  const [dimension, setDimension] = useState('thumbnail_style')
  const [variantA, setVariantA] = useState('')
  const [variantB, setVariantB] = useState('')
  const [keywordA, setKeywordA] = useState('')
  const [keywordB, setKeywordB] = useState('')
  const [metric, setMetric] = useState('views')
  const [result, setResult] = useState(null)
  const [running, setRunning] = useState(false)
  const [testError, setTestError] = useState('')

  const dimChoices = useMemo(() => {
    if (!options) return []
    if (dimension === 'thumbnail_style') return options.thumbnail_styles || []
    return (options.categories || []).filter((c) => c !== 'all')
  }, [options, dimension])

  const runTest = useCallback(async () => {
    setRunning(true)
    setTestError('')
    setResult(null)
    try {
      const query = buildQuery(filters)
      let url
      if (mode === 'attribute') {
        const params = new URLSearchParams(query)
        params.set('dimension', dimension)
        params.set('variant_a', variantA)
        params.set('variant_b', variantB)
        params.set('metric', metric)
        url = `${API_BASE}/analysis/ab-test?${params}`
      } else {
        const params = new URLSearchParams(query)
        params.set('keyword_a', keywordA)
        params.set('keyword_b', keywordB)
        params.set('metric', metric)
        url = `${API_BASE}/analysis/ab-test/title?${params}`
      }
      const resp = await fetch(url)
      const data = await resp.json()
      if (data.error) throw new Error(data.error)
      setResult(data)
    } catch (err) {
      setTestError(err.message)
    } finally {
      setRunning(false)
    }
  }, [mode, dimension, variantA, variantB, keywordA, keywordB, metric, filters])

  const canRun = mode === 'attribute'
    ? variantA && variantB && variantA !== variantB
    : keywordA.trim() && keywordB.trim() && keywordA.trim().toLowerCase() !== keywordB.trim().toLowerCase()

  return (
    <section className="card ab-test-section">
      <h3>A/B Test Analysis</h3>

      <div className="ab-mode-toggle">
        <button className={`btn ${mode === 'attribute' ? 'btn-active' : 'btn-secondary'}`} onClick={() => setMode('attribute')}>
          Thumbnail / Category
        </button>
        <button className={`btn ${mode === 'title' ? 'btn-active' : 'btn-secondary'}`} onClick={() => setMode('title')}>
          Title Keywords
        </button>
      </div>

      <div className="ab-controls">
        {mode === 'attribute' ? (
          <>
            <label>
              Dimension
              <select value={dimension} onChange={(e) => { setDimension(e.target.value); setVariantA(''); setVariantB('') }}>
                <option value="thumbnail_style">Thumbnail style</option>
                <option value="category">Category</option>
              </select>
            </label>
            <label>
              Variant A
              <select value={variantA} onChange={(e) => setVariantA(e.target.value)}>
                <option value="">Select...</option>
                {dimChoices.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
            <label>
              Variant B
              <select value={variantB} onChange={(e) => setVariantB(e.target.value)}>
                <option value="">Select...</option>
                {dimChoices.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
          </>
        ) : (
          <>
            <label>
              Keyword A
              <input type="text" value={keywordA} onChange={(e) => setKeywordA(e.target.value)} placeholder='e.g. "magic"' />
            </label>
            <label>
              Keyword B
              <input type="text" value={keywordB} onChange={(e) => setKeywordB(e.target.value)} placeholder='e.g. "brave"' />
            </label>
          </>
        )}
        <label>
          Metric
          <select value={metric} onChange={(e) => setMetric(e.target.value)}>
            {AB_METRICS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        </label>
        <div className="ab-run">
          <button className="btn btn-primary" onClick={runTest} disabled={!canRun || running}>
            {running ? 'Running\u2026' : 'Run Test'}
          </button>
        </div>
      </div>

      {testError ? <div className="ab-error">{testError}</div> : null}

      {result ? <ABTestResult result={result} /> : null}
    </section>
  )
}

ABTestSection.propTypes = {
  options: PropTypes.object,
  filters: PropTypes.object.isRequired,
}

/** Renders the full A/B test result: variant stats, test output, effect size, and recommendation. */
function ABTestResult({ result }) {
  const { variant_a: a, variant_b: b, test, effect, recommendation } = result

  const sigClass = test.p_value < 0.05 ? 'ab-sig-yes' : 'ab-sig-no'

  return (
    <div className="ab-result">
      <div className="ab-variants">
        <div className="ab-variant-card">
          <div className="ab-variant-label">Variant A</div>
          <div className="ab-variant-name">{a.label}</div>
          <div className="ab-stat-grid">
            <div><span className="ab-stat-label">n</span> {a.n}</div>
            <div><span className="ab-stat-label">Mean</span> {formatFloat(a.mean, 4)}</div>
            <div><span className="ab-stat-label">Median</span> {formatFloat(a.median, 4)}</div>
            <div><span className="ab-stat-label">Std</span> {formatFloat(a.std, 4)}</div>
          </div>
        </div>
        <div className="ab-vs">vs</div>
        <div className="ab-variant-card">
          <div className="ab-variant-label">Variant B</div>
          <div className="ab-variant-name">{b.label}</div>
          <div className="ab-stat-grid">
            <div><span className="ab-stat-label">n</span> {b.n}</div>
            <div><span className="ab-stat-label">Mean</span> {formatFloat(b.mean, 4)}</div>
            <div><span className="ab-stat-label">Median</span> {formatFloat(b.median, 4)}</div>
            <div><span className="ab-stat-label">Std</span> {formatFloat(b.std, 4)}</div>
          </div>
        </div>
      </div>

      <div className="ab-stats-row">
        <div className="ab-stat-box">
          <div className="ab-stat-title">Statistical Test</div>
          <div className="ab-stat-detail">{test.method}</div>
          <div>t = {formatFloat(test.t_statistic, 4)}, df = {formatFloat(test.degrees_of_freedom, 1)}</div>
          <div className={sigClass}>
            p = {test.p_value < 0.0001 ? '<0.0001' : formatFloat(test.p_value, 4)}
            <span className="ab-sig-badge">{test.significance}</span>
          </div>
        </div>
        <div className="ab-stat-box">
          <div className="ab-stat-title">Effect Size</div>
          <div>Cohen&apos;s d = {formatFloat(effect.cohens_d, 4)} ({effect.effect_size})</div>
          <div>Difference: {formatFloat(effect.difference_pct, 1)}%</div>
          <div>95% CI: [{formatFloat(effect.ci_95_lower, 2)}, {formatFloat(effect.ci_95_upper, 2)}]</div>
        </div>
      </div>

      <div className={`ab-recommendation ${test.p_value < 0.05 ? 'ab-rec-sig' : 'ab-rec-neutral'}`}>
        {recommendation}
      </div>
    </div>
  )
}

ABTestResult.propTypes = {
  result: PropTypes.shape({
    variant_a: PropTypes.object.isRequired,
    variant_b: PropTypes.object.isRequired,
    test: PropTypes.object.isRequired,
    effect: PropTypes.object.isRequired,
    recommendation: PropTypes.string.isRequired,
  }).isRequired,
}

/* ── Anomalies + Similarity ───────────────────────────────────── */

/** Top-anomalies table alongside a video-similarity search panel. */
function AnomalySection({ anomalies, similar, videos, selectedVideoId, setSelectedVideoId }) {
  return (
    <section className="two-column-grid anomaly-grid">
      <DataTable
        title="Top anomalies"
        columns={[
          { key: 'video_id', label: 'ID' },
          { key: 'title', label: 'Title' },
          { key: 'views', label: 'Views' },
          { key: 'engagement_rate_pct', label: 'Engagement %' },
          { key: 'anomaly_score', label: 'Anomaly score' },
        ]}
        rows={anomalies?.items || []}
      />
      <div className="card similar-card">
        <h3>Similar content search</h3>
        <div className="similar-selector">
          <label>
            Anchor video
            <select value={selectedVideoId} onChange={(event) => setSelectedVideoId(event.target.value)}>
              {videos.slice(0, 50).map((video) => (
                <option key={video.video_id} value={video.video_id}>
                  {video.video_id} &middot; {video.title}
                </option>
              ))}
            </select>
          </label>
        </div>
        {similar?.source ? (
          <div className="similar-panel">
            <div className="source-box">
              <div className="cluster-title">{similar.source.title}</div>
              <div>{similar.source.category} &middot; {similar.source.thumbnail_style}</div>
              <div>{formatInteger(similar.source.views)} views &middot; {formatFloat(similar.source.engagement_rate_pct, 2)}% engagement</div>
            </div>
            <div className="similar-list">
              {(similar.items || []).map((item) => (
                <div key={item.video_id} className="similar-item">
                  <div className="cluster-title">{item.title}</div>
                  <div>{item.category} &middot; {item.thumbnail_style}</div>
                  <div>{formatInteger(item.views)} views &middot; sim {formatFloat(item.similarity, 3)}</div>
                </div>
              ))}
            </div>
          </div>
        ) : <div className="empty-state">Select a video to inspect title neighbours.</div>}
      </div>
    </section>
  )
}

AnomalySection.propTypes = {
  anomalies: PropTypes.shape({ items: PropTypes.array }),
  similar: PropTypes.shape({
    source: PropTypes.shape({ title: PropTypes.string, category: PropTypes.string, thumbnail_style: PropTypes.string, views: PropTypes.number, engagement_rate_pct: PropTypes.number }),
    items: PropTypes.array,
  }),
  videos: PropTypes.array.isRequired,
  selectedVideoId: PropTypes.string.isRequired,
  setSelectedVideoId: PropTypes.func.isRequired,
}

/* ── App ──────────────────────────────────────────────────────── */

/** Root component: wires filter controls, data hook, and all dashboard sections together. */
export default function App() {
  const {
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
  } = useDashboardData()

  return (
    <div className="page">
      <header className="hero">
        <div>
          <p className="eyebrow">Pilot project</p>
          <h1>Content Performance Insights Dashboard</h1>
          <p className="lead">
            End-to-end ETL, analytics, anomaly detection, clustering, and title similarity for video performance data.
          </p>
        </div>
        <div className="card validation-card">
          <h3>Data Quality</h3>
          <div>Rows loaded: {validation?.rows_loaded ?? '-'}</div>
          <div>Duplicates removed: {validation?.duplicate_video_ids_removed ?? '-'}</div>
          <div>Date range: {validation?.date_range?.min} to {validation?.date_range?.max}</div>
          <div className="card-actions">
            <UploadSection onUpload={uploadCsv} uploading={uploading} />
            {summary?.totals ? <DownloadButtons filters={filters} /> : null}
          </div>
        </div>
      </header>

      <section className="filters card">
        <div className="filter-grid">
          <label>
            Category
            <select name="category" value={filters.category} onChange={handleFilterChange}>
              {options?.categories?.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </label>
          <label>
            Start date
            <input type="date" name="start_date" value={filters.start_date} onChange={handleFilterChange} />
          </label>
          <label>
            End date
            <input type="date" name="end_date" value={filters.end_date} onChange={handleFilterChange} />
          </label>
        </div>
      </section>

      {error ? (
        <div className="error-banner" role="alert">
          <span>{error}</span>
          <button className="dismiss-btn" onClick={clearError} aria-label="Dismiss error">&times;</button>
        </div>
      ) : null}

      {loading ? <div className="loading" role="status">Loading analytics&hellip;</div> : null}

      {!loading && summary?.totals ? (
        <>
          <OverviewSection summary={summary} />
          <ChartsSection summary={summary} trends={trends} />
          <ClusterSection clusters={clusters} />
          <TrendsSection trends={trends} />
          <ExperimentSection clusterExperiment={clusterExperiment} anomalyExperiment={anomalyExperiment} />
          <ABTestSection options={options} filters={filters} />
          <AnomalySection
            anomalies={anomalies}
            similar={similar}
            videos={videos}
            selectedVideoId={selectedVideoId}
            setSelectedVideoId={setSelectedVideoId}
          />

          <section className="card">
            <h3>Recommendations</h3>
            <ul className="recommendation-list">
              {(summary.recommendations || []).map((item, idx) => <li key={idx}>{item}</li>)}
            </ul>
          </section>
        </>
      ) : null}
    </div>
  )
}
