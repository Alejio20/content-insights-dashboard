"""
CSV ingestion, schema validation, and derived-metric enrichment.

``VideoDatasetLoader`` reads a CSV (from disk or raw upload bytes),
validates it against the expected 10-column schema, and computes
engagement rates, rolling averages, and other derived columns before
returning a ``DataLoadResult`` bundle.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

# The exact column set every input CSV must contain -- no more, no fewer.
EXPECTED_COLUMNS = [
    "video_id",
    "title",
    "category",
    "publish_date",
    "views",
    "watch_time_seconds",
    "likes",
    "comments",
    "shares",
    "thumbnail_style",
]
NUMERIC_COLUMNS = ["views", "watch_time_seconds", "likes", "comments", "shares"]
TEXT_COLUMNS = ["title", "category", "thumbnail_style"]


@dataclass(slots=True)
class DataLoadResult:
    """Validated DataFrame paired with a quality-audit report dict."""
    frame: pd.DataFrame
    validation_report: dict[str, Any]


class DataValidationError(ValueError):
    """Raised when the input CSV does not match the expected schema."""


class VideoDatasetLoader:
    """Loads, validates, and enriches a video-performance CSV dataset.

    Validation enforces column presence, type coercion, non-negativity,
    and strictly positive view counts.  The enrichment step adds per-view
    rates, temporal features, and rolling averages so downstream
    analytics can operate on a ready-to-query DataFrame.
    """

    def __init__(self, csv_path: Path):
        self.csv_path = Path(csv_path)

    def load(self) -> DataLoadResult:
        """Read the CSV from disk, validate, enrich, and return results."""
        if not self.csv_path.exists():
            raise FileNotFoundError(f"Dataset not found: {self.csv_path}")
        df = pd.read_csv(self.csv_path)
        return self._validate_and_enrich(df, str(self.csv_path))

    @classmethod
    def load_from_bytes(cls, raw: bytes, filename: str) -> DataLoadResult:
        """Parse an in-memory CSV byte string (used for file uploads)."""
        import io
        df = pd.read_csv(io.BytesIO(raw))
        return cls._validate_and_enrich(df, filename)

    @classmethod
    def _validate_and_enrich(cls, df: pd.DataFrame, source_name: str) -> DataLoadResult:
        """Run the full validation pipeline, enrich, and build an audit report.

        Raises ``DataValidationError`` for schema mismatches, unparseable
        values, negatives, or zero-view rows.
        """

        # ── Schema check ─────────────────────────────────────────
        missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
        extra = [c for c in df.columns if c not in EXPECTED_COLUMNS]
        if missing or extra:
            raise DataValidationError(
                f"Dataset schema mismatch. Missing={missing or '[]'}, Extra={extra or '[]'}"
            )

        # ── Deduplication ────────────────────────────────────────
        original_rows = len(df)
        duplicate_rows = int(df.duplicated(subset=["video_id"]).sum())
        if duplicate_rows:
            df = df.drop_duplicates(subset=["video_id"], keep="first").copy()

        # ── Type coercion & integrity checks ─────────────────────
        df["video_id"] = pd.to_numeric(df["video_id"], errors="coerce")
        invalid_video_ids = int(df["video_id"].isna().sum())
        if invalid_video_ids:
            raise DataValidationError(f"Found {invalid_video_ids} invalid video_id values")
        df["video_id"] = df["video_id"].astype(int)

        for column in TEXT_COLUMNS:
            df[column] = df[column].astype(str).str.strip()

        df["publish_date"] = pd.to_datetime(df["publish_date"], errors="coerce")
        invalid_dates = int(df["publish_date"].isna().sum())
        if invalid_dates:
            raise DataValidationError(f"Found {invalid_dates} invalid publish_date values")

        for column in NUMERIC_COLUMNS:
            df[column] = pd.to_numeric(df[column], errors="coerce")
        invalid_numeric = int(df[NUMERIC_COLUMNS].isna().any(axis=1).sum())
        if invalid_numeric:
            raise DataValidationError(f"Found {invalid_numeric} rows with invalid numeric values")

        # ── Business-rule checks ─────────────────────────────────
        negative_rows = int((df[NUMERIC_COLUMNS] < 0).any(axis=1).sum())
        if negative_rows:
            raise DataValidationError(f"Found {negative_rows} rows with negative metrics")

        zero_view_rows = int((df["views"] <= 0).sum())
        if zero_view_rows:
            raise DataValidationError("views must be strictly positive for all rows")

        # ── Enrichment & audit report ────────────────────────────
        df = cls._add_derived_metrics(df)
        report = {
            "source_path": source_name,
            "rows_read": int(original_rows),
            "rows_loaded": int(len(df)),
            "duplicate_video_ids_removed": duplicate_rows,
            "invalid_video_ids": invalid_video_ids,
            "invalid_dates": invalid_dates,
            "invalid_numeric_rows": invalid_numeric,
            "negative_metric_rows": negative_rows,
            "zero_view_rows": zero_view_rows,
            "date_range": {
                "min": df["publish_date"].min().date().isoformat(),
                "max": df["publish_date"].max().date().isoformat(),
            },
        }
        return DataLoadResult(frame=df, validation_report=report)

    @staticmethod
    def _add_derived_metrics(df: pd.DataFrame) -> pd.DataFrame:
        """Compute per-view rates, temporal features, and rolling averages.

        All derived columns are safe to compute because the validation
        step already guarantees views > 0 and no NaN numerics.
        """
        enriched = df.copy()

        # Per-view engagement and interaction rates
        enriched["engagement_total"] = enriched[["likes", "comments", "shares"]].sum(axis=1)
        enriched["engagement_rate"] = enriched["engagement_total"] / enriched["views"]
        enriched["engagement_rate_pct"] = enriched["engagement_rate"] * 100.0
        enriched["avg_watch_time_seconds"] = enriched["watch_time_seconds"] / enriched["views"]
        enriched["like_rate"] = enriched["likes"] / enriched["views"]
        enriched["comment_rate"] = enriched["comments"] / enriched["views"]
        enriched["share_rate"] = enriched["shares"] / enriched["views"]
        enriched["watch_time_hours"] = enriched["watch_time_seconds"] / 3600.0

        # Temporal grouping helpers
        enriched["publish_month"] = enriched["publish_date"].dt.to_period("M").astype(str)
        enriched["publish_weekday"] = enriched["publish_date"].dt.day_name()
        enriched["title_word_count"] = enriched["title"].str.split().str.len()

        # Days since publish (relative to the newest video in the dataset)
        latest = enriched["publish_date"].max()
        enriched["days_since_publish"] = (latest - enriched["publish_date"]).dt.days
        # clip(lower=1) prevents division by zero for same-day publishes
        enriched["views_per_day"] = enriched["views"] / enriched["days_since_publish"].clip(lower=1)

        enriched = enriched.sort_values("publish_date").reset_index(drop=True)

        # Date-indexed rolling averages for trend visualisation
        enriched["rolling_views_7d"] = (
            enriched.set_index("publish_date")["views"]
            .rolling("7D", min_periods=1).mean()
            .values
        )
        enriched["rolling_views_30d"] = (
            enriched.set_index("publish_date")["views"]
            .rolling("30D", min_periods=1).mean()
            .values
        )
        enriched["rolling_engagement_30d"] = (
            enriched.set_index("publish_date")["engagement_rate_pct"]
            .rolling("30D", min_periods=1).mean()
            .values
        )

        return enriched
