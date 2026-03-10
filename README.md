# Content Performance Insights Dashboard — by Humble

## Setup

### Prerequisites
- Python 3.10+
- Node.js 18+

### 1) Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend will run on `http://127.0.0.1:8000`.

### 2) Frontend
Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend will run on `http://127.0.0.1:5173` and will call the backend at `http://127.0.0.1:8000` by default.

If needed, set a custom API base URL:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

### 3) Running Tests
```bash
# Backend (19 tests)
cd backend
pytest tests/ -v

# Frontend (9 tests)
cd frontend
npm test
```

### 4) Linting
```bash
# Backend
cd backend
ruff check .

# Frontend
cd frontend
npm run lint
```

## Approach
I built the project as a small full-stack analytics product instead of only a notebook, because the task asks for both insight generation and a usable dashboard.

### Data Processing
The backend loads the CSV, validates the schema, removes duplicate video IDs, checks for invalid dates and numeric values, and calculates derived metrics:
- engagement total and engagement rate
- average watch time per view
- like, comment, and share rates
- publish month, weekday, and day-of-year
- title word count and character count
- days since publish and views per day
- 7-day and 30-day rolling averages for views and engagement

This logic lives in `backend/app/data_loader.py` so the ETL is explicit and reusable.

### Analytics
I implemented four analytics layers so the dashboard goes beyond simple descriptive charts.

1. **Trend detection** — category, thumbnail style, and weekday lift tables; correlation analysis (including new features like title word count, days since publish, views per day); monthly performance trend lines; rolling 30-day trends; and a lightweight metadata signal check using a cross-validated Ridge model.

2. **Clustering** — videos are grouped by standardised performance features. The backend automatically picks the best cluster count from a small search range using silhouette score. Each cluster is labelled with a data-driven narrative derived from quantile ranking.

3. **Anomaly detection** — Isolation Forest flags videos with unusually strong or weak combinations of reach, engagement, and watch time.

4. **Title similarity search** — TF-IDF-based title embeddings find similar content names without needing an external API key.

### Experiment Tracking
The dashboard includes a model comparison panel that runs clustering with every k in {2..6} and anomaly detection with contamination rates from 2% to 10%. Results (silhouette scores, inertia, anomaly counts) are displayed side by side so users can evaluate trade-offs.

### CSV Upload & WebSocket Live Refresh
Users can upload a new CSV file directly from the dashboard. The backend validates it, replaces the in-memory dataset, and broadcasts a refresh signal to all connected clients via WebSocket. Every open browser tab updates automatically.

### Downloadable Reports
Filtered data can be exported as CSV or PDF. The PDF report includes summary charts (category averages, monthly trends, top-10 table) generated server-side with matplotlib.

### Product Design Choices
The frontend is a React dashboard that supports:
- category, date range filtering
- overview metric cards
- cluster scatter map with narratives
- anomaly table
- similar title lookup
- experiment comparison tables
- interactive A/B test analysis for thumbnails, categories, and title keywords
- actionable recommendation panel
- CSV upload with live WebSocket refresh
- one-click CSV and PDF report downloads

I used native React plus lightweight SVG charts with axis labels and gridlines instead of adding a heavy charting library.

## Key Insights
These findings come from the provided synthetic dataset, so they should be interpreted as directional rather than causal.

1. **Reach is driven much more by absolute reactions than by percentage engagement.**
   Likes, comments, and shares correlate strongly with views, while engagement rate itself is close to neutral relative to raw reach.

2. **Category and thumbnail style differences exist, but they are modest.**
   The visible metadata alone is not a strong explanation for performance.

3. **The metadata signal is weak.**
   The small cross-validated R-squared from the metadata-only model means fields like category, thumbnail style, and month explain only a small part of view variation. This points to missing features, not failed modelling.

4. **Clusters are more useful than single averages.**
   The clustering step separates broad reach, high engagement, niche sticky content, and more balanced performers — a better decision tool than one overall average.

5. **Anomalies are worth editorial review.**
   The anomaly detector highlights unusual combinations — very high engagement on relatively low reach, or the opposite.

## Technical Decisions

| Decision | Rationale |
|---|---|
| **FastAPI** | Lightweight, fast to wire up, and gives a clean local API for the React frontend. |
| **React + Vite** | Required by the brief. Kept dependency-light so it runs locally with no extra setup. |
| **TF-IDF over external embeddings** | Titles are short and synthetic. TF-IDF is sufficient for local similarity and avoids API keys or network calls. |
| **KMeans + Isolation Forest** | Fast, interpretable, and appropriate for a take-home where explainability matters more than model complexity. |
| **Quantile-based cluster labels** | Cluster narratives are derived from the data distribution rather than hardcoded thresholds, so they adapt if the dataset changes. |
| **Metadata signal model** | Prevents overclaiming. Measures how much signal is actually present in the available metadata. |
| **WebSocket for live refresh** | After CSV upload the backend broadcasts to all connected clients, keeping every open tab in sync without polling. |
| **Server-side PDF generation** | Uses matplotlib + PdfPages so reports are self-contained and don't require the frontend to be running. |
| **Welch's t-test for A/B analysis** | Proper unequal-variance t-test with Cohen's d effect size and 95% CI gives actionable, statistically grounded comparisons between content variants. |
| **Vitest + pytest + GitHub Actions CI** | Automated test suites for both frontend and backend with CI on every push and pull request. |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `GET` | `/validation` | Data quality report |
| `GET` | `/filters` | Available filter options |
| `GET` | `/videos` | Paginated video list (filterable) |
| `GET` | `/dashboard/summary` | Overview metrics and recommendations |
| `GET` | `/analysis/trends` | Trend and correlation analysis |
| `GET` | `/analysis/clusters` | Cluster analysis with scatter points |
| `GET` | `/analysis/anomalies` | Anomaly detection results |
| `GET` | `/analysis/similar/{video_id}` | Title similarity search |
| `GET` | `/analysis/ab-test` | A/B test for thumbnail style or category |
| `GET` | `/analysis/ab-test/title` | A/B test for title keyword comparison |
| `POST` | `/upload` | Upload new CSV dataset |
| `GET` | `/experiments/clusters` | Cluster k-value comparison |
| `GET` | `/experiments/anomalies` | Anomaly contamination comparison |
| `GET` | `/reports/csv` | Download filtered data as CSV |
| `GET` | `/reports/pdf` | Download insight report as PDF |
| `WS` | `/ws` | WebSocket for live refresh signals |

## Repository Structure
```text
├── .github/workflows/
│   └── ci.yml                          # GitHub Actions CI pipeline
│
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI routes and middleware
│   │   ├── analytics.py                # Clustering, anomalies, A/B tests, reports
│   │   ├── data_loader.py              # CSV ingestion, validation, derived metrics
│   │   ├── store.py                    # In-memory data store and WebSocket manager
│   │   └── config.py                   # Constants and feature ranges
│   ├── tests/
│   │   └── test_api.py                 # 19 API integration tests
│   ├── requirements.txt
│   └── ruff.toml                       # Python linter config
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx                     # Root component and dashboard layout
│   │   ├── main.jsx                    # Entry point
│   │   ├── styles.css                  # Global styles (dark theme, responsive)
│   │   ├── components/
│   │   │   ├── BarChart.jsx            # Horizontal bar chart (SVG)
│   │   │   ├── LineChart.jsx           # Time-series line chart (SVG)
│   │   │   ├── ScatterPlot.jsx         # Cluster scatter plot (SVG)
│   │   │   ├── DataTable.jsx           # Sortable data table
│   │   │   └── MetricCard.jsx          # KPI summary card
│   │   ├── hooks/
│   │   │   └── useDashboardData.js     # Data fetching, filters, WebSocket
│   │   └── test/
│   │       ├── BarChart.test.jsx       # 9 component tests (Vitest)
│   │       ├── DataTable.test.jsx
│   │       ├── MetricCard.test.jsx
│   │       └── ScatterPlot.test.jsx
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── eslint.config.js
│
└── data/
    └── sample_videos.csv               # 1 000 rows, 10 columns
```

## Given More Time
- Add user authentication and multi-tenant data isolation
- Add persistent storage (PostgreSQL) with migration support
- Add streaming upload progress for large CSV files
- Add scheduled report delivery via email
