from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import MiniBatchKMeans
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import IsolationForest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from sklearn.metrics import r2_score, silhouette_score
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from scipy import stats as scipy_stats

from .config import CLUSTER_RANGE, DEFAULT_ANOMALY_CONTAMINATION, EXPERIMENT_CONTAMINATION_RANGE, RANDOM_STATE

AB_METRICS = ["views", "engagement_rate_pct", "avg_watch_time_seconds", "like_rate", "comment_rate", "share_rate"]


@dataclass(slots=True)
class FilterOptions:
    category: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class AnalyticsService:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.feature_columns = [
            "views",
            "engagement_rate",
            "avg_watch_time_seconds",
            "share_rate",
            "comment_rate",
            "like_rate",
        ]
        self._similarity_matrix = None
        self._title_vectorizer = None

    def filter_frame(self, filters: FilterOptions | None = None) -> pd.DataFrame:
        filters = filters or FilterOptions()
        frame = self.df.copy()
        if filters.category and filters.category.lower() != "all":
            frame = frame.loc[frame["category"] == filters.category]
        if filters.start_date:
            frame = frame.loc[frame["publish_date"] >= pd.Timestamp(filters.start_date)]
        if filters.end_date:
            frame = frame.loc[frame["publish_date"] <= pd.Timestamp(filters.end_date)]
        return frame.reset_index(drop=True)

    def get_filter_options(self) -> dict[str, Any]:
        return {
            "categories": ["all", *sorted(self.df["category"].unique().tolist())],
            "thumbnail_styles": sorted(self.df["thumbnail_style"].unique().tolist()),
            "date_range": {
                "min": self.df["publish_date"].min().date().isoformat(),
                "max": self.df["publish_date"].max().date().isoformat(),
            },
        }

    def get_videos(self, filters: FilterOptions | None = None, limit: int = 100) -> list[dict[str, Any]]:
        frame = self.filter_frame(filters).sort_values("views", ascending=False).head(limit)
        columns = [
            "video_id",
            "title",
            "category",
            "publish_date",
            "thumbnail_style",
            "views",
            "engagement_rate_pct",
            "avg_watch_time_seconds",
        ]
        return self._serialize_records(frame[columns])

    def get_summary(self, filters: FilterOptions | None = None) -> dict[str, Any]:
        frame = self.filter_frame(filters)
        if frame.empty:
            return self._empty_response()

        totals = {
            "videos": int(len(frame)),
            "total_views": int(frame["views"].sum()),
            "total_watch_time_hours": round(float(frame["watch_time_hours"].sum()), 2),
            "avg_views": round(float(frame["views"].mean()), 2),
            "avg_engagement_rate_pct": round(float(frame["engagement_rate_pct"].mean()), 3),
            "avg_watch_time_seconds": round(float(frame["avg_watch_time_seconds"].mean()), 2),
            "median_views": int(frame["views"].median()),
        }

        top_video = frame.sort_values("views", ascending=False).iloc[0]
        best_engagement = frame.sort_values("engagement_rate", ascending=False).iloc[0]

        by_category = (
            frame.groupby("category")
            .agg(
                videos=("video_id", "count"),
                avg_views=("views", "mean"),
                avg_engagement_rate_pct=("engagement_rate_pct", "mean"),
                avg_watch_time_seconds=("avg_watch_time_seconds", "mean"),
            )
            .reset_index()
            .sort_values("avg_views", ascending=False)
        )

        by_thumbnail = (
            frame.groupby("thumbnail_style")
            .agg(
                videos=("video_id", "count"),
                avg_views=("views", "mean"),
                avg_engagement_rate_pct=("engagement_rate_pct", "mean"),
                avg_watch_time_seconds=("avg_watch_time_seconds", "mean"),
            )
            .reset_index()
            .sort_values("avg_engagement_rate_pct", ascending=False)
        )

        monthly = (
            frame.groupby("publish_month")
            .agg(
                videos=("video_id", "count"),
                avg_views=("views", "mean"),
                avg_engagement_rate_pct=("engagement_rate_pct", "mean"),
            )
            .reset_index()
        )

        return {
            "totals": totals,
            "top_video_by_views": self._row_to_card(top_video),
            "top_video_by_engagement": self._row_to_card(best_engagement),
            "by_category": self._serialize_records(by_category),
            "by_thumbnail_style": self._serialize_records(by_thumbnail),
            "monthly": self._serialize_records(monthly),
            "recommendations": self._make_recommendations(frame),
        }

    def get_trend_analysis(self, filters: FilterOptions | None = None) -> dict[str, Any]:
        frame = self.filter_frame(filters)
        if frame.empty:
            return self._empty_response()

        correlation_columns = [
            "views",
            "engagement_rate_pct",
            "avg_watch_time_seconds",
            "likes",
            "comments",
            "shares",
            "title_word_count",
            "days_since_publish",
            "views_per_day",
        ]
        correlation_series = (
            frame[correlation_columns]
            .corr(numeric_only=True)["views"]
            .drop("views")
            .dropna()
            .sort_values(ascending=False)
        )

        category_lift = (
            frame.groupby("category")[["views", "engagement_rate_pct", "avg_watch_time_seconds"]]
            .mean()
            .reset_index()
            .sort_values("engagement_rate_pct", ascending=False)
        )
        thumbnail_lift = (
            frame.groupby("thumbnail_style")[["views", "engagement_rate_pct", "avg_watch_time_seconds"]]
            .mean()
            .reset_index()
            .sort_values("engagement_rate_pct", ascending=False)
        )

        metadata_r2 = self._metadata_signal_score(frame)
        token_lift = self._token_lift(frame, target_column="views", top_n=12)

        weekday_lift = (
            frame.groupby("publish_weekday")[["views", "engagement_rate_pct", "avg_watch_time_seconds"]]
            .mean()
            .reset_index()
            .sort_values("engagement_rate_pct", ascending=False)
        )

        rolling = None
        if "rolling_views_30d" in frame.columns:
            rolling_frame = (
                frame[["publish_date", "rolling_views_7d", "rolling_views_30d", "rolling_engagement_30d"]]
                .copy()
            )
            rolling_frame["publish_date"] = rolling_frame["publish_date"].dt.date.astype(str)
            rolling = self._serialize_records(rolling_frame.tail(60))

        return {
            "correlations_to_views": [
                {"metric": name, "correlation": round(float(value), 4)}
                for name, value in correlation_series.items()
            ],
            "category_lift": self._serialize_records(category_lift),
            "thumbnail_lift": self._serialize_records(thumbnail_lift),
            "weekday_lift": self._serialize_records(weekday_lift),
            "rolling_trends": rolling,
            "metadata_signal": metadata_r2,
            "title_token_lift": token_lift,
        }

    def get_cluster_analysis(self, filters: FilterOptions | None = None) -> dict[str, Any]:
        frame = self.filter_frame(filters)
        if frame.empty:
            return self._empty_response()

        scaled = StandardScaler().fit_transform(frame[self.feature_columns])
        best_k = 2
        best_score = -1.0
        best_labels = None
        for k in CLUSTER_RANGE:
            if len(frame) <= k:
                continue
            model = MiniBatchKMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=5, max_iter=100, batch_size=256)
            labels = model.fit_predict(scaled)
            score = silhouette_score(scaled, labels)
            if score > best_score:
                best_k = k
                best_score = float(score)
                best_labels = labels
        if best_labels is None:
            best_labels = np.zeros(len(frame), dtype=int)

        enriched = frame.copy()
        enriched["cluster_id"] = best_labels
        cluster_summary = (
            enriched.groupby("cluster_id")
            .agg(
                videos=("video_id", "count"),
                avg_views=("views", "mean"),
                avg_engagement_rate_pct=("engagement_rate_pct", "mean"),
                avg_watch_time_seconds=("avg_watch_time_seconds", "mean"),
                avg_share_rate=("share_rate", "mean"),
            )
            .reset_index()
        )
        cluster_summary["label"] = self._label_clusters(cluster_summary)

        sample_points = enriched[
            [
                "video_id",
                "title",
                "category",
                "views",
                "engagement_rate_pct",
                "cluster_id",
            ]
        ].sort_values("views", ascending=False).head(250)

        return {
            "best_k": int(best_k),
            "silhouette_score": round(best_score, 4),
            "clusters": self._serialize_records(cluster_summary.sort_values("videos", ascending=False)),
            "points": self._serialize_records(sample_points),
        }

    def get_anomalies(self, filters: FilterOptions | None = None, contamination: float = DEFAULT_ANOMALY_CONTAMINATION) -> dict[str, Any]:
        frame = self.filter_frame(filters)
        if frame.empty:
            return self._empty_response()

        scaled = StandardScaler().fit_transform(frame[self.feature_columns])
        model = IsolationForest(contamination=contamination, random_state=RANDOM_STATE)
        model.fit(scaled)
        anomaly_flag = model.predict(scaled)
        anomaly_score = -model.score_samples(scaled)

        enriched = frame.copy()
        enriched["is_anomaly"] = anomaly_flag == -1
        enriched["anomaly_score"] = anomaly_score

        anomalies = enriched.loc[enriched["is_anomaly"]].sort_values("anomaly_score", ascending=False)
        normal_range = {
            "views_q1": int(frame["views"].quantile(0.25)),
            "views_q3": int(frame["views"].quantile(0.75)),
            "engagement_q1": round(float(frame["engagement_rate_pct"].quantile(0.25)), 3),
            "engagement_q3": round(float(frame["engagement_rate_pct"].quantile(0.75)), 3),
        }

        columns = [
            "video_id",
            "title",
            "category",
            "thumbnail_style",
            "publish_date",
            "views",
            "engagement_rate_pct",
            "avg_watch_time_seconds",
            "anomaly_score",
        ]
        return {
            "count": int(len(anomalies)),
            "contamination": contamination,
            "normal_range": normal_range,
            "items": self._serialize_records(anomalies[columns].head(30)),
        }

    def get_similar_videos(self, video_id: int, top_n: int = 5) -> dict[str, Any]:
        if self._similarity_matrix is None or self._title_vectorizer is None:
            self._build_title_similarity_index()

        matches = self.df.index[self.df["video_id"] == video_id].tolist()
        if not matches:
            raise KeyError(f"video_id {video_id} not found")
        idx = matches[0]
        scores = self._similarity_matrix[idx]
        nearest = np.argsort(scores)[::-1]
        nearest = [i for i in nearest if i != idx][:top_n]

        base_video = self.df.iloc[idx]
        similar = self.df.iloc[nearest][
            [
                "video_id",
                "title",
                "category",
                "thumbnail_style",
                "views",
                "engagement_rate_pct",
            ]
        ].copy()
        similar["similarity"] = [float(scores[i]) for i in nearest]

        return {
            "source": self._row_to_card(base_video),
            "items": self._serialize_records(similar.sort_values("similarity", ascending=False)),
        }

    def _build_title_similarity_index(self) -> None:
        vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z]+\b",
        )
        matrix = vectorizer.fit_transform(self.df["title"])
        self._title_vectorizer = vectorizer
        self._similarity_matrix = cosine_similarity(matrix, dense_output=False).toarray()

    def _metadata_signal_score(self, frame: pd.DataFrame) -> dict[str, Any]:
        X = frame[["category", "thumbnail_style", "publish_month"]].copy()
        y = np.log1p(frame["views"])
        model = Pipeline(
            steps=[
                (
                    "prep",
                    ColumnTransformer(
                        transformers=[
                            (
                                "categorical",
                                OneHotEncoder(handle_unknown="ignore"),
                                ["category", "thumbnail_style", "publish_month"],
                            )
                        ],
                        remainder="drop",
                    ),
                ),
                ("regressor", Ridge(alpha=1.0, random_state=RANDOM_STATE)),
            ]
        )
        splitter = KFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
        pred = cross_val_predict(model, X, y, cv=splitter)
        score = r2_score(y, pred)
        model.fit(X, y)
        names = model.named_steps["prep"].get_feature_names_out().tolist()
        coefs = model.named_steps["regressor"].coef_.ravel().tolist()
        ranked = sorted(zip(names, coefs), key=lambda item: abs(item[1]), reverse=True)[:10]
        return {
            "cross_validated_r2": round(float(score), 4),
            "top_features": [
                {"feature": feature.replace("categorical__", ""), "coefficient": round(float(value), 4)}
                for feature, value in ranked
            ],
            "interpretation": (
                "Values near zero mean the available metadata explains little of the variation in views. "
                "This is useful product feedback because it suggests performance is likely driven by missing factors "
                "such as topic novelty, recommendation system exposure, or audience retention beyond title/style alone."
            ),
        }

    @staticmethod
    def _token_lift(frame: pd.DataFrame, target_column: str, top_n: int = 10) -> list[dict[str, Any]]:
        if frame.empty:
            return []
        threshold = frame[target_column].quantile(0.75)
        high_mask = (frame[target_column] >= threshold).values
        vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z]+\b",
        )
        matrix = vectorizer.fit_transform(frame["title"])
        lift = np.asarray(matrix[high_mask].mean(axis=0) - matrix[~high_mask].mean(axis=0)).ravel()
        terms = np.asarray(vectorizer.get_feature_names_out())
        best_idx = np.argsort(lift)[-top_n:][::-1]
        return [
            {"term": str(terms[i]), "lift": round(float(lift[i]), 4)}
            for i in best_idx
            if lift[i] > 0
        ]

    @staticmethod
    def _label_clusters(summary: pd.DataFrame) -> list[str]:
        views_median = summary["avg_views"].median()
        engagement_median = summary["avg_engagement_rate_pct"].median()
        share_median = summary["avg_share_rate"].median()

        labels: list[str] = []
        for _, row in summary.iterrows():
            high_views = row["avg_views"] >= views_median
            high_engagement = row["avg_engagement_rate_pct"] >= engagement_median
            high_share = row["avg_share_rate"] >= share_median

            if high_views and high_engagement:
                labels.append("High reach, high engagement")
            elif not high_views and high_engagement:
                labels.append("Niche but sticky")
            elif high_views and not high_engagement:
                labels.append("Broad reach, lighter interaction")
            elif high_share:
                labels.append("Share friendly")
            else:
                labels.append("Balanced performers")
        return labels

    def _make_recommendations(self, frame: pd.DataFrame) -> list[str]:
        category = (
            frame.groupby("category")["engagement_rate_pct"].mean().sort_values(ascending=False).index[0]
        )
        thumb = (
            frame.groupby("thumbnail_style")["engagement_rate_pct"].mean().sort_values(ascending=False).index[0]
        )
        high_watch = frame.sort_values("avg_watch_time_seconds", ascending=False).iloc[0]
        return [
            f"Use {thumb} thumbnails as a test priority because they currently lead engagement in this slice.",
            f"{category.title()} videos are the strongest engagement segment right now, so they are a good place to double down.",
            f"Investigate videos similar to '{high_watch['title']}' because exceptionally high watch time often signals repeatable content pacing.",
            "Track more features next, especially video duration, upload time, and audience source, because current metadata explains only a small share of view variance.",
        ]

    @staticmethod
    def _row_to_card(row: pd.Series) -> dict[str, Any]:
        return {
            "video_id": int(row["video_id"]),
            "title": str(row["title"]),
            "category": str(row["category"]),
            "thumbnail_style": str(row["thumbnail_style"]),
            "publish_date": pd.Timestamp(row["publish_date"]).date().isoformat(),
            "views": int(row["views"]),
            "engagement_rate_pct": round(float(row["engagement_rate_pct"]), 3),
            "avg_watch_time_seconds": round(float(row["avg_watch_time_seconds"]), 2),
        }

    @staticmethod
    def _serialize_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        for record in frame.to_dict(orient="records"):
            clean_record: dict[str, Any] = {}
            for key, value in record.items():
                if isinstance(value, (pd.Timestamp, pd.Period)):
                    clean_record[key] = str(value)
                elif isinstance(value, (np.integer,)):
                    clean_record[key] = int(value)
                elif isinstance(value, (np.floating, float)):
                    clean_record[key] = round(float(value), 4)
                else:
                    clean_record[key] = value
            serialized.append(clean_record)
        return serialized

    def run_cluster_experiment(self, filters: FilterOptions | None = None) -> dict[str, Any]:
        frame = self.filter_frame(filters)
        if frame.empty:
            return self._empty_response()

        scaled = StandardScaler().fit_transform(frame[self.feature_columns])
        runs: list[dict[str, Any]] = []
        for k in CLUSTER_RANGE:
            if len(frame) <= k:
                continue
            model = MiniBatchKMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=5, max_iter=100, batch_size=256)
            labels = model.fit_predict(scaled)
            sil = silhouette_score(scaled, labels)
            inertia = float(model.inertia_)

            enriched = frame.copy()
            enriched["cluster_id"] = labels
            summary = (
                enriched.groupby("cluster_id")
                .agg(
                    videos=("video_id", "count"),
                    avg_views=("views", "mean"),
                    avg_engagement_rate_pct=("engagement_rate_pct", "mean"),
                )
                .reset_index()
            )
            runs.append({
                "k": int(k),
                "silhouette_score": round(float(sil), 4),
                "inertia": round(inertia, 2),
                "cluster_sizes": summary["videos"].tolist(),
            })

        return {"runs": runs, "feature_columns": self.feature_columns}

    def run_anomaly_experiment(self, filters: FilterOptions | None = None) -> dict[str, Any]:
        frame = self.filter_frame(filters)
        if frame.empty:
            return self._empty_response()

        scaled = StandardScaler().fit_transform(frame[self.feature_columns])
        runs: list[dict[str, Any]] = []
        for rate in EXPERIMENT_CONTAMINATION_RANGE:
            model = IsolationForest(contamination=rate, random_state=RANDOM_STATE)
            model.fit(scaled)
            flags = model.predict(scaled)
            scores = -model.score_samples(scaled)
            n_anomalies = int((flags == -1).sum())
            runs.append({
                "contamination": rate,
                "anomalies_found": n_anomalies,
                "pct_flagged": round(n_anomalies / len(frame) * 100, 2),
                "mean_anomaly_score": round(float(scores[flags == -1].mean()), 4) if n_anomalies else 0,
                "mean_normal_score": round(float(scores[flags == 1].mean()), 4),
            })

        return {"runs": runs, "total_videos": len(frame)}

    def generate_csv_report(self, filters: FilterOptions | None = None) -> str:
        frame = self.filter_frame(filters)
        if frame.empty:
            return ""

        export_cols = [
            "video_id", "title", "category", "publish_date", "thumbnail_style",
            "views", "likes", "comments", "shares", "watch_time_seconds",
            "engagement_rate_pct", "avg_watch_time_seconds", "like_rate",
            "comment_rate", "share_rate", "title_word_count", "days_since_publish",
            "views_per_day", "publish_weekday",
        ]
        available = [c for c in export_cols if c in frame.columns]
        out = frame[available].copy()
        out["publish_date"] = out["publish_date"].dt.date
        return out.to_csv(index=False)

    def generate_pdf_report(self, filters: FilterOptions | None = None) -> bytes:
        import io as _io

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages

        frame = self.filter_frame(filters)
        summary = self.get_summary(filters)
        trends = self.get_trend_analysis(filters)
        clusters = self.get_cluster_analysis(filters)
        anomalies = self.get_anomalies(filters)

        buf = _io.BytesIO()
        with PdfPages(buf) as pdf:
            self._pdf_title_page(pdf, plt, frame)
            if frame.empty:
                return buf.getvalue()
            self._pdf_overview_page(pdf, plt, summary)
            self._pdf_category_thumbnail_page(pdf, plt, frame)
            self._pdf_monthly_page(pdf, plt, frame)
            self._pdf_weekday_page(pdf, plt, frame)
            self._pdf_correlation_page(pdf, plt, trends)
            self._pdf_cluster_page(pdf, plt, clusters)
            self._pdf_anomaly_page(pdf, plt, anomalies)
            self._pdf_top_videos_page(pdf, plt, frame)
            self._pdf_recommendations_page(pdf, plt, summary)

        return buf.getvalue()

    @staticmethod
    def _pdf_make_table(ax, col_labels, rows, title):
        ax.axis("off")
        if rows:
            tbl = ax.table(cellText=rows, colLabels=col_labels, loc="center", cellLoc="left")
            tbl.auto_set_font_size(False)
            tbl.set_fontsize(8)
            tbl.scale(1, 1.3)
            for (r, _), cell in tbl.get_celld().items():
                if r == 0:
                    cell.set_facecolor("#334155")
                    cell.set_text_props(color="white", weight="bold")
                else:
                    cell.set_facecolor("#f8fafc" if r % 2 == 0 else "#ffffff")
        ax.set_title(title, pad=20, fontsize=13, weight="bold")

    @staticmethod
    def _pdf_title_page(pdf, plt, frame):
        fig, ax = plt.subplots(figsize=(10, 3))
        ax.axis("off")
        ax.text(0.5, 0.75, "Content Performance Insights Report", fontsize=22, ha="center", weight="bold")
        ax.text(0.5, 0.45, f"{len(frame)} videos analysed", fontsize=13, ha="center", color="gray")
        if not frame.empty:
            date_min = frame["publish_date"].min().date().isoformat()
            date_max = frame["publish_date"].max().date().isoformat()
            ax.text(0.5, 0.2, f"Date range: {date_min}  to  {date_max}", fontsize=11, ha="center", color="gray")
        pdf.savefig(fig)
        plt.close(fig)

    @staticmethod
    def _pdf_overview_page(pdf, plt, summary):
        t = summary.get("totals", {})
        if not t:
            return
        metrics = [
            ("Videos", f"{t['videos']:,}"),
            ("Total Views", f"{t['total_views']:,}"),
            ("Avg Views", f"{t['avg_views']:,.0f}"),
            ("Median Views", f"{t['median_views']:,}"),
            ("Avg Engagement %", f"{t['avg_engagement_rate_pct']:.3f}%"),
            ("Avg Watch Time", f"{t['avg_watch_time_seconds']:.1f} sec"),
            ("Total Watch Time", f"{t['total_watch_time_hours']:,.1f} hrs"),
        ]
        fig, ax = plt.subplots(figsize=(10, 3))
        ax.axis("off")
        rows = [[m[0], m[1]] for m in metrics]
        tbl = ax.table(cellText=rows, colLabels=["Metric", "Value"], loc="center", cellLoc="left")
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(10)
        tbl.scale(1, 1.6)
        for (r, _), cell in tbl.get_celld().items():
            if r == 0:
                cell.set_facecolor("#334155")
                cell.set_text_props(color="white", weight="bold")
            else:
                cell.set_facecolor("#f8fafc" if r % 2 == 0 else "#ffffff")
        ax.set_title("Overview Metrics", pad=20, fontsize=14, weight="bold")
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

    @staticmethod
    def _pdf_category_thumbnail_page(pdf, plt, frame):
        cat = frame.groupby("category")["views"].mean().sort_values(ascending=False)
        thumb = frame.groupby("thumbnail_style")["engagement_rate_pct"].mean().sort_values(ascending=False)
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
        cat.plot.bar(ax=ax1, color="#38bdf8")
        ax1.set_title("Avg Views by Category")
        ax1.set_ylabel("Views")
        ax1.tick_params(axis="x", rotation=30)
        thumb.plot.bar(ax=ax2, color="#22c55e")
        ax2.set_title("Avg Engagement % by Thumbnail Style")
        ax2.set_ylabel("Engagement %")
        ax2.tick_params(axis="x", rotation=30)
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

    @staticmethod
    def _pdf_monthly_page(pdf, plt, frame):
        monthly = frame.groupby("publish_month").agg(
            avg_views=("views", "mean"),
            avg_engagement=("engagement_rate_pct", "mean"),
        ).reset_index()
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
        ax1.plot(monthly["publish_month"], monthly["avg_views"], marker="o", color="#38bdf8")
        ax1.fill_between(range(len(monthly)), monthly["avg_views"], alpha=0.1, color="#38bdf8")
        ax1.set_title("Monthly Avg Views")
        ax1.set_ylabel("Views")
        ax1.tick_params(axis="x", rotation=45)
        ax2.plot(monthly["publish_month"], monthly["avg_engagement"], marker="o", color="#22c55e")
        ax2.fill_between(range(len(monthly)), monthly["avg_engagement"], alpha=0.1, color="#22c55e")
        ax2.set_title("Monthly Avg Engagement %")
        ax2.set_ylabel("Engagement %")
        ax2.tick_params(axis="x", rotation=45)
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

    @staticmethod
    def _pdf_weekday_page(pdf, plt, frame):
        if "publish_weekday" not in frame.columns:
            return
        weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        wd = frame.groupby("publish_weekday")[["views", "engagement_rate_pct", "avg_watch_time_seconds"]].mean()
        wd = wd.reindex([d for d in weekday_order if d in wd.index])
        if wd.empty:
            return
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
        wd["avg_watch_time_seconds"].plot.bar(ax=ax1, color="#f59e0b")
        ax1.set_title("Avg Watch Time by Weekday")
        ax1.set_ylabel("Seconds")
        ax1.tick_params(axis="x", rotation=30)
        wd["engagement_rate_pct"].plot.bar(ax=ax2, color="#a855f7")
        ax2.set_title("Avg Engagement % by Weekday")
        ax2.set_ylabel("Engagement %")
        ax2.tick_params(axis="x", rotation=30)
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

    @staticmethod
    def _pdf_correlation_page(pdf, plt, trends):
        corrs = trends.get("correlations_to_views", [])
        tokens = trends.get("title_token_lift", [])
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        if corrs:
            names = [c["metric"] for c in corrs]
            vals = [c["correlation"] for c in corrs]
            colors = ["#22c55e" if v >= 0 else "#ef4444" for v in vals]
            ax1.barh(names[::-1], vals[::-1], color=colors[::-1])
            ax1.set_title("Correlation to Views")
            ax1.axvline(0, color="gray", linewidth=0.5)
        else:
            ax1.axis("off")
            ax1.text(0.5, 0.5, "No correlation data", ha="center")
        if tokens:
            terms = [t["term"] for t in tokens[:10]]
            lifts = [t["lift"] for t in tokens[:10]]
            ax2.barh(terms[::-1], lifts[::-1], color="#38bdf8")
            ax2.set_title("Title Token Lift (top terms in high-view titles)")
        else:
            ax2.axis("off")
            ax2.text(0.5, 0.5, "No token data", ha="center")
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

    def _pdf_cluster_page(self, pdf, plt, clusters):
        if "clusters" not in clusters:
            return
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        cluster_colors = ["#38bdf8", "#22c55e", "#f59e0b", "#f97316", "#a855f7", "#ef4444"]
        points = clusters.get("points", [])
        if points:
            for pt in points:
                cid = int(pt.get("cluster_id", 0))
                ax1.scatter(pt["views"], pt["engagement_rate_pct"], c=cluster_colors[cid % len(cluster_colors)], s=12, alpha=0.6)
            ax1.set_xlabel("Views")
            ax1.set_ylabel("Engagement %")
            ax1.set_title(f"Cluster Map (k={clusters.get('best_k', '?')}, silhouette={clusters.get('silhouette_score', '?')})")
        else:
            ax1.axis("off")
        cl = clusters["clusters"]
        rows = [[c.get("cluster_id", ""), c.get("label", ""), c.get("videos", ""),
                 f"{c.get('avg_views', 0):,.0f}", f"{c.get('avg_engagement_rate_pct', 0):.2f}%",
                 f"{c.get('avg_watch_time_seconds', 0):.1f}s"] for c in cl]
        self._pdf_make_table(ax2, ["ID", "Label", "Videos", "Avg Views", "Engagement %", "Watch Time"], rows, "Cluster Summary")
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

    def _pdf_anomaly_page(self, pdf, plt, anomalies):
        items = anomalies.get("items", [])
        if not items:
            return
        rows = [[a.get("video_id", ""), a.get("title", "")[:35], a.get("category", ""),
                 f"{a.get('views', 0):,}", f"{a.get('engagement_rate_pct', 0):.2f}%",
                 f"{a.get('anomaly_score', 0):.4f}"] for a in items[:15]]
        fig, ax = plt.subplots(figsize=(11, 5))
        self._pdf_make_table(ax, ["ID", "Title", "Category", "Views", "Engagement %", "Anomaly Score"], rows,
                             f"Top Anomalies ({anomalies.get('count', 0)} flagged at {anomalies.get('contamination', '')} contamination)")
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

    def _pdf_top_videos_page(self, pdf, plt, frame):
        top = frame.sort_values("views", ascending=False).head(10)
        rows = [[int(r["video_id"]), r["title"][:35], r["category"],
                 f"{int(r['views']):,}", f"{r['engagement_rate_pct']:.2f}%",
                 f"{r['avg_watch_time_seconds']:.1f}s"] for _, r in top.iterrows()]
        fig, ax = plt.subplots(figsize=(11, 4.5))
        self._pdf_make_table(ax, ["ID", "Title", "Category", "Views", "Engagement %", "Watch Time"], rows, "Top 10 Videos by Views")
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

    @staticmethod
    def _pdf_recommendations_page(pdf, plt, summary):
        recs = summary.get("recommendations", [])
        if not recs:
            return
        fig, ax = plt.subplots(figsize=(10, 3))
        ax.axis("off")
        text = "\n\n".join(f"  {i+1}.  {r}" for i, r in enumerate(recs))
        ax.text(0.05, 0.95, text, fontsize=10, va="top", ha="left", wrap=True,
                transform=ax.transAxes, linespacing=1.6, family="sans-serif")
        ax.set_title("Recommendations", pad=20, fontsize=14, weight="bold")
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

    def run_ab_test(
        self,
        filters: FilterOptions | None = None,
        dimension: str = "thumbnail_style",
        variant_a: str = "",
        variant_b: str = "",
        metric: str = "views",
    ) -> dict[str, Any]:
        frame = self.filter_frame(filters)
        if frame.empty:
            return self._empty_response()

        if dimension not in ("thumbnail_style", "category"):
            return {"error": "dimension must be thumbnail_style or category"}
        if metric not in AB_METRICS:
            return {"error": f"metric must be one of {AB_METRICS}"}

        group_a = frame.loc[frame[dimension] == variant_a, metric].dropna()
        group_b = frame.loc[frame[dimension] == variant_b, metric].dropna()

        if len(group_a) < 2 or len(group_b) < 2:
            return {"error": "Each variant needs at least 2 observations for a test."}

        return self._compare_groups(group_a, group_b, variant_a, variant_b, metric)

    def run_title_ab_test(
        self,
        filters: FilterOptions | None = None,
        keyword_a: str = "",
        keyword_b: str = "",
        metric: str = "views",
    ) -> dict[str, Any]:
        frame = self.filter_frame(filters)
        if frame.empty:
            return self._empty_response()
        if metric not in AB_METRICS:
            return {"error": f"metric must be one of {AB_METRICS}"}

        titles_lower = frame["title"].str.lower()
        mask_a = titles_lower.str.contains(keyword_a.lower(), regex=False)
        mask_b = titles_lower.str.contains(keyword_b.lower(), regex=False)

        group_a = frame.loc[mask_a, metric].dropna()
        group_b = frame.loc[mask_b, metric].dropna()

        label_a = f'"{keyword_a}"'
        label_b = f'"{keyword_b}"'

        if len(group_a) < 2 or len(group_b) < 2:
            return {"error": "Each keyword group needs at least 2 matching videos."}

        return self._compare_groups(group_a, group_b, label_a, label_b, metric)

    @staticmethod
    def _compare_groups(
        group_a: pd.Series,
        group_b: pd.Series,
        label_a: str,
        label_b: str,
        metric: str,
    ) -> dict[str, Any]:
        mean_a, mean_b = float(group_a.mean()), float(group_b.mean())
        std_a, std_b = float(group_a.std(ddof=1)), float(group_b.std(ddof=1))
        n_a, n_b = len(group_a), len(group_b)

        t_stat, p_value = scipy_stats.ttest_ind(group_a, group_b, equal_var=False)

        pooled_std = np.sqrt(((n_a - 1) * std_a ** 2 + (n_b - 1) * std_b ** 2) / (n_a + n_b - 2)) if (n_a + n_b) > 2 else 1.0
        cohens_d = (mean_a - mean_b) / pooled_std if pooled_std > 0 else 0.0

        se_diff = np.sqrt(std_a ** 2 / n_a + std_b ** 2 / n_b)
        df = ((std_a ** 2 / n_a + std_b ** 2 / n_b) ** 2 /
              ((std_a ** 2 / n_a) ** 2 / (n_a - 1) + (std_b ** 2 / n_b) ** 2 / (n_b - 1)))
        t_crit = scipy_stats.t.ppf(0.975, df) if df > 0 else 1.96
        ci_lower = (mean_a - mean_b) - t_crit * se_diff
        ci_upper = (mean_a - mean_b) + t_crit * se_diff

        if p_value < 0.01:
            significance = "highly significant"
        elif p_value < 0.05:
            significance = "significant"
        elif p_value < 0.10:
            significance = "marginally significant"
        else:
            significance = "not significant"

        abs_d = abs(cohens_d)
        if abs_d >= 0.8:
            effect_label = "large"
        elif abs_d >= 0.5:
            effect_label = "medium"
        elif abs_d >= 0.2:
            effect_label = "small"
        else:
            effect_label = "negligible"

        winner = label_a if mean_a > mean_b else label_b
        diff_pct = abs(mean_a - mean_b) / max(min(abs(mean_a), abs(mean_b)), 1e-9) * 100

        return {
            "metric": metric,
            "variant_a": {
                "label": label_a,
                "n": n_a,
                "mean": round(mean_a, 4),
                "std": round(std_a, 4),
                "median": round(float(group_a.median()), 4),
            },
            "variant_b": {
                "label": label_b,
                "n": n_b,
                "mean": round(mean_b, 4),
                "std": round(std_b, 4),
                "median": round(float(group_b.median()), 4),
            },
            "test": {
                "method": "Welch's t-test (unequal variance)",
                "t_statistic": round(float(t_stat), 4),
                "p_value": round(float(p_value), 6),
                "degrees_of_freedom": round(float(df), 2),
                "significance": significance,
            },
            "effect": {
                "cohens_d": round(float(cohens_d), 4),
                "effect_size": effect_label,
                "difference_pct": round(diff_pct, 2),
                "ci_95_lower": round(float(ci_lower), 4),
                "ci_95_upper": round(float(ci_upper), 4),
            },
            "recommendation": (
                f"{winner} outperforms on {metric} "
                f"({effect_label} effect, p={round(float(p_value), 4)}, "
                f"difference {round(diff_pct, 1)}%). "
                + (
                    "The result is statistically significant — consider scaling the winner."
                    if p_value < 0.05
                    else "The result is not statistically significant — gather more data before acting."
                )
            ),
        }

    @staticmethod
    def _empty_response() -> dict[str, Any]:
        return {"message": "No rows match the selected filters."}
