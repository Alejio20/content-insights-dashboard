from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .analytics import AnalyticsService, FilterOptions
from .data_loader import DataValidationError
from .store import data_store, ws_manager

logger = logging.getLogger(__name__)

app = FastAPI(title="Content Performance Insights Dashboard API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Check backend logs for details."},
    )


@app.exception_handler(DataValidationError)
async def validation_exception_handler(request: Request, exc: DataValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


def _service() -> AnalyticsService:
    return AnalyticsService(data_store.result.frame)


def parse_filters(
    category: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> FilterOptions:
    return FilterOptions(category=category, start_date=start_date, end_date=end_date)


# ── WebSocket ────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


# ── Core endpoints ───────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/validation")
def validation_report() -> dict:
    return data_store.result.validation_report


@app.get("/filters")
def filter_options() -> dict:
    return _service().get_filter_options()


@app.get("/videos")
def videos(
    filters: FilterOptions = Depends(parse_filters),
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict:
    return {"items": _service().get_videos(filters, limit=limit)}


@app.get("/dashboard/summary")
def dashboard_summary(filters: FilterOptions = Depends(parse_filters)) -> dict:
    return _service().get_summary(filters)


# ── Analysis endpoints ───────────────────────────────────────────

@app.get("/analysis/trends")
def trend_analysis(filters: FilterOptions = Depends(parse_filters)) -> dict:
    return _service().get_trend_analysis(filters)


@app.get("/analysis/clusters")
def cluster_analysis(filters: FilterOptions = Depends(parse_filters)) -> dict:
    return _service().get_cluster_analysis(filters)


@app.get("/analysis/anomalies")
def anomaly_analysis(
    filters: FilterOptions = Depends(parse_filters),
    contamination: float = Query(default=0.04, gt=0.0, lt=0.5),
) -> dict:
    return _service().get_anomalies(filters, contamination=contamination)


@app.get("/analysis/similar/{video_id}")
def similar_videos(video_id: int, top_n: int = Query(default=5, ge=1, le=20)) -> dict:
    try:
        return _service().get_similar_videos(video_id=video_id, top_n=top_n)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Upload endpoint ──────────────────────────────────────────────

@app.post("/upload")
async def upload_csv(file: UploadFile) -> dict:
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")

    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 50 MB)")

    result = await data_store.replace_from_bytes(raw, file.filename)

    await ws_manager.broadcast({"type": "data_refreshed", "rows": result.validation_report["rows_loaded"]})

    return {
        "status": "ok",
        "filename": file.filename,
        "validation": result.validation_report,
    }


# ── Experiment tracking ─────────────────────────────────────────

@app.get("/experiments/clusters")
def cluster_experiment(filters: FilterOptions = Depends(parse_filters)) -> dict:
    return _service().run_cluster_experiment(filters)


@app.get("/experiments/anomalies")
def anomaly_experiment(filters: FilterOptions = Depends(parse_filters)) -> dict:
    return _service().run_anomaly_experiment(filters)


# ── A/B test analysis ────────────────────────────────────────────

@app.get("/analysis/ab-test")
def ab_test(
    filters: FilterOptions = Depends(parse_filters),
    dimension: str = Query(default="thumbnail_style"),
    variant_a: str = Query(default=""),
    variant_b: str = Query(default=""),
    metric: str = Query(default="views"),
) -> dict:
    return _service().run_ab_test(filters, dimension=dimension, variant_a=variant_a, variant_b=variant_b, metric=metric)


@app.get("/analysis/ab-test/title")
def title_ab_test(
    filters: FilterOptions = Depends(parse_filters),
    keyword_a: str = Query(default=""),
    keyword_b: str = Query(default=""),
    metric: str = Query(default="views"),
) -> dict:
    return _service().run_title_ab_test(filters, keyword_a=keyword_a, keyword_b=keyword_b, metric=metric)


# ── Report downloads ────────────────────────────────────────────

@app.get("/reports/csv")
def download_csv_report(filters: FilterOptions = Depends(parse_filters)) -> Response:
    csv_str = _service().generate_csv_report(filters)
    return Response(
        content=csv_str,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=insights_report.csv"},
    )


@app.get("/reports/pdf")
def download_pdf_report(filters: FilterOptions = Depends(parse_filters)) -> StreamingResponse:
    import io
    pdf_bytes = _service().generate_pdf_report(filters)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=insights_report.pdf"},
    )
