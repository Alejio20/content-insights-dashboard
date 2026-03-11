"""
Application configuration and constants.

Centralises file paths, ML hyper-parameters, and environment-level thread
limits so every module draws from a single source of truth.
"""

from __future__ import annotations

import os
from pathlib import Path

# Restrict linear-algebra libraries to one thread each to avoid contention
# when serving concurrent requests behind an ASGI server.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT_DIR / "data" / "sample_videos.csv"

# ── ML / analysis defaults ───────────────────────────────────────
DEFAULT_ANOMALY_CONTAMINATION = 0.04          # IsolationForest expected outlier fraction
CLUSTER_RANGE = range(2, 7)                   # k values evaluated during cluster selection
EXPERIMENT_CONTAMINATION_RANGE = [0.02, 0.04, 0.06, 0.08, 0.10]
RANDOM_STATE = 42                             # Fixed seed for reproducible results
