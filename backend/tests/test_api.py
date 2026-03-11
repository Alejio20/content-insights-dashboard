"""
Integration tests for the FastAPI backend.

Each test hits a live ``TestClient`` backed by the sample CSV, verifying
status codes, response structure, and key business invariants across
all API endpoints (health, filters, videos, summary, trends, clusters,
anomalies, similarity, experiments, A/B tests, reports, and uploads).
"""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

SAMPLE_CSV = Path(__file__).resolve().parents[2] / "data" / "sample_videos.csv"


# ── Health / core ────────────────────────────────────────────────

def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_validation_report() -> None:
    response = client.get("/validation")
    payload = response.json()
    assert response.status_code == 200
    assert payload["rows_loaded"] > 0
    assert "date_range" in payload


def test_filter_options() -> None:
    response = client.get("/filters")
    payload = response.json()
    assert response.status_code == 200
    assert "all" in payload["categories"]
    assert len(payload["thumbnail_styles"]) >= 1
    assert "min" in payload["date_range"]


def test_videos_returns_list() -> None:
    response = client.get("/videos?limit=5")
    payload = response.json()
    assert response.status_code == 200
    assert len(payload["items"]) <= 5
    assert "video_id" in payload["items"][0]


def test_videos_filter_by_category() -> None:
    opts = client.get("/filters").json()
    cat = [c for c in opts["categories"] if c != "all"][0]
    response = client.get(f"/videos?category={cat}&limit=10")
    payload = response.json()
    assert response.status_code == 200
    assert all(v["category"] == cat for v in payload["items"])


# ── Summary ──────────────────────────────────────────────────────

def test_summary_contains_metrics() -> None:
    response = client.get("/dashboard/summary")
    payload = response.json()
    assert response.status_code == 200
    assert payload["totals"]["videos"] == 1000
    assert payload["totals"]["total_views"] > 0
    assert len(payload["by_category"]) >= 1
    assert len(payload["recommendations"]) >= 1


def test_summary_with_date_filter() -> None:
    response = client.get("/dashboard/summary?start_date=2024-01-01&end_date=2024-12-31")
    payload = response.json()
    assert response.status_code == 200
    assert payload["totals"]["videos"] <= 1000


# ── Trends ───────────────────────────────────────────────────────

def test_trend_analysis() -> None:
    response = client.get("/analysis/trends")
    payload = response.json()
    assert response.status_code == 200
    assert len(payload["correlations_to_views"]) >= 1
    assert "weekday_lift" in payload
    assert "rolling_trends" in payload
    assert payload["metadata_signal"]["cross_validated_r2"] is not None


# ── Clusters ─────────────────────────────────────────────────────

def test_cluster_endpoint() -> None:
    response = client.get("/analysis/clusters")
    payload = response.json()
    assert response.status_code == 200
    assert payload["best_k"] >= 2
    assert len(payload["clusters"]) >= 2
    assert "label" in payload["clusters"][0]


# ── Anomalies ────────────────────────────────────────────────────

def test_anomaly_endpoint() -> None:
    response = client.get("/analysis/anomalies")
    payload = response.json()
    assert response.status_code == 200
    assert payload["count"] >= 0
    assert "normal_range" in payload


def test_anomaly_custom_contamination() -> None:
    response = client.get("/analysis/anomalies?contamination=0.1")
    payload = response.json()
    assert response.status_code == 200
    assert payload["contamination"] == 0.1


# ── Similarity ───────────────────────────────────────────────────

def test_similarity_endpoint() -> None:
    response = client.get("/analysis/similar/1")
    payload = response.json()
    assert response.status_code == 200
    assert payload["source"]["video_id"] == 1
    assert len(payload["items"]) == 5


def test_similarity_not_found() -> None:
    response = client.get("/analysis/similar/999999")
    assert response.status_code == 404


# ── Experiments ──────────────────────────────────────────────────

def test_cluster_experiment() -> None:
    response = client.get("/experiments/clusters")
    payload = response.json()
    assert response.status_code == 200
    assert len(payload["runs"]) >= 2
    assert "silhouette_score" in payload["runs"][0]
    assert "inertia" in payload["runs"][0]


def test_anomaly_experiment() -> None:
    response = client.get("/experiments/anomalies")
    payload = response.json()
    assert response.status_code == 200
    assert len(payload["runs"]) >= 2
    assert "anomalies_found" in payload["runs"][0]
    assert payload["total_videos"] > 0


# ── Reports ──────────────────────────────────────────────────────

def test_csv_report_download() -> None:
    response = client.get("/reports/csv")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert "video_id" in response.text


def test_pdf_report_download() -> None:
    response = client.get("/reports/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert len(response.content) > 100


# ── Upload ───────────────────────────────────────────────────────

def test_upload_csv() -> None:
    with open(SAMPLE_CSV, "rb") as f:
        response = client.post("/upload", files={"file": ("test.csv", f, "text/csv")})
    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["validation"]["rows_loaded"] > 0


def test_upload_rejects_non_csv() -> None:
    response = client.post("/upload", files={"file": ("test.txt", b"hello", "text/plain")})
    assert response.status_code == 400


# ── A/B Test ────────────────────────────────────────────────────

def test_ab_test_thumbnail() -> None:
    opts = client.get("/filters").json()
    styles = opts["thumbnail_styles"]
    assert len(styles) >= 2
    response = client.get(
        f"/analysis/ab-test?dimension=thumbnail_style&variant_a={styles[0]}&variant_b={styles[1]}&metric=views"
    )
    payload = response.json()
    assert response.status_code == 200
    assert "variant_a" in payload
    assert "variant_b" in payload
    assert "test" in payload
    assert "effect" in payload
    assert payload["test"]["method"] == "Welch's t-test (unequal variance)"
    assert "recommendation" in payload


def test_ab_test_category() -> None:
    opts = client.get("/filters").json()
    categories = [c for c in opts["categories"] if c != "all"]
    assert len(categories) >= 2
    response = client.get(
        f"/analysis/ab-test?dimension=category&variant_a={categories[0]}&variant_b={categories[1]}&metric=engagement_rate_pct"
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["variant_a"]["n"] > 0
    assert payload["variant_b"]["n"] > 0
    assert payload["effect"]["cohens_d"] is not None


def test_ab_test_title_keywords() -> None:
    response = client.get(
        "/analysis/ab-test/title?keyword_a=magic&keyword_b=brave&metric=views"
    )
    payload = response.json()
    assert response.status_code == 200
    assert "variant_a" in payload
    assert payload["variant_a"]["label"] == '"magic"'
    assert payload["variant_b"]["label"] == '"brave"'


def test_ab_test_same_variant_error() -> None:
    opts = client.get("/filters").json()
    style = opts["thumbnail_styles"][0]
    response = client.get(
        f"/analysis/ab-test?dimension=thumbnail_style&variant_a={style}&variant_b=nonexistent_style&metric=views"
    )
    payload = response.json()
    assert "error" in payload


def test_ab_test_invalid_dimension() -> None:
    response = client.get(
        "/analysis/ab-test?dimension=invalid&variant_a=a&variant_b=b&metric=views"
    )
    payload = response.json()
    assert "error" in payload


def test_ab_test_invalid_metric() -> None:
    response = client.get(
        "/analysis/ab-test?dimension=thumbnail_style&variant_a=a&variant_b=b&metric=invalid"
    )
    payload = response.json()
    assert "error" in payload
