from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT_DIR / "data" / "sample_videos.csv"
DEFAULT_ANOMALY_CONTAMINATION = 0.04
CLUSTER_RANGE = range(2, 7)
EXPERIMENT_CONTAMINATION_RANGE = [0.02, 0.04, 0.06, 0.08, 0.10]
RANDOM_STATE = 42
