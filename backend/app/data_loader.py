from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

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
    frame: pd.DataFrame
    validation_report: dict[str, Any]


class DataValidationError(ValueError):
    """Raised when the input CSV does not match the expected schema."""


class VideoDatasetLoader:
    def __init__(self, csv_path: Path):
        self.csv_path = Path(csv_path)

    def load(self) -> DataLoadResult:
        if not self.csv_path.exists():
            raise FileNotFoundError(f"Dataset not found: {self.csv_path}")
        df = pd.read_csv(self.csv_path)
        return self._validate_and_enrich(df, str(self.csv_path))

    @classmethod
    def load_from_bytes(cls, raw: bytes, filename: str) -> DataLoadResult:
        import io
        df = pd.read_csv(io.BytesIO(raw))
        return cls._validate_and_enrich(df, filename)

    @classmethod
    def _validate_and_enrich(cls, df: pd.DataFrame, source_name: str) -> DataLoadResult:
        missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
        extra = [c for c in df.columns if c not in EXPECTED_COLUMNS]
        if missing or extra:
            raise DataValidationError(
                f"Dataset schema mismatch. Missing={missing or '[]'}, Extra={extra or '[]'}"
            )

        original_rows = len(df)
        duplicate_rows = int(df.duplicated(subset=["video_id"]).sum())
        if duplicate_rows:
            df = df.drop_duplicates(subset=["video_id"], keep="first").copy()

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

        negative_rows = int((df[NUMERIC_COLUMNS] < 0).any(axis=1).sum())
        if negative_rows:
            raise DataValidationError(f"Found {negative_rows} rows with negative metrics")

        zero_view_rows = int((df["views"] <= 0).sum())
        if zero_view_rows:
            raise DataValidationError("views must be strictly positive for all rows")

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
        enriched = df.copy()
        enriched["engagement_total"] = enriched[["likes", "comments", "shares"]].sum(axis=1)
        enriched["engagement_rate"] = enriched["engagement_total"] / enriched["views"]
        enriched["engagement_rate_pct"] = enriched["engagement_rate"] * 100.0
        enriched["avg_watch_time_seconds"] = enriched["watch_time_seconds"] / enriched["views"]
        enriched["like_rate"] = enriched["likes"] / enriched["views"]
        enriched["comment_rate"] = enriched["comments"] / enriched["views"]
        enriched["share_rate"] = enriched["shares"] / enriched["views"]
        enriched["watch_time_hours"] = enriched["watch_time_seconds"] / 3600.0
        enriched["publish_month"] = enriched["publish_date"].dt.to_period("M").astype(str)
        enriched["publish_weekday"] = enriched["publish_date"].dt.day_name()

        enriched["title_word_count"] = enriched["title"].str.split().str.len()

        latest = enriched["publish_date"].max()
        enriched["days_since_publish"] = (latest - enriched["publish_date"]).dt.days

        enriched["views_per_day"] = enriched["views"] / enriched["days_since_publish"].clip(lower=1)

        enriched = enriched.sort_values("publish_date").reset_index(drop=True)

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
