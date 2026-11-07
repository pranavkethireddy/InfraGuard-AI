"""Backblaze Drive Stats (Q1 2025) -> drive-day rows labelled "fails within 30 days".

Real data-center hard drives. Each daily CSV has one row per drive; `failure=1` on the
drive's last day before removal for failure. Nothing here is synthetic.

Labelling (no future leakage into features):
- An observation day d uses only that day's SMART values.
- label = 1 if the same drive records failure=1 on a day f with 0 <= f - d < HORIZON_DAYS.
- Only days d with d + HORIZON_DAYS <= last day of the quarter are used, so every label
  is fully observed inside the quarter.
Sampling (recorded, and undone with weights at evaluation):
- Every drive that fails in the quarter is kept; NEG_DRIVE_RATE of the other drives
  (deterministic hash of serial_number) are kept; every DAY_STRIDE-th day is kept.
"""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

SOURCE_URL = "https://f001.backblazeb2.com/file/Backblaze-Hard-Drive-Data/data_Q1_2025.zip"
ZIP_NAME = "data_Q1_2025.zip"
ZIP_SHA256 = "7a230565f72fdb3882c05fdcfab361c801e9a545ba18543899fc7618174171ec"
DATASET_VERSION = "backblaze-drive-stats-2025Q1"
LICENSE = "Backblaze Drive Stats; free to use with attribution to Backblaze"

HORIZON_DAYS = 30
NEG_DRIVE_RATE = 0.02
DAY_STRIDE = 2

# raw SMART column -> contract feature name (all raw counts except temperature/hours)
FEATURE_COLUMNS = {
    "smart_5_raw": "reallocated_sectors",
    "smart_187_raw": "reported_uncorrectable",
    "smart_188_raw": "command_timeout",
    "smart_197_raw": "pending_sectors",
    "smart_198_raw": "offline_uncorrectable",
    "smart_199_raw": "crc_errors",
    "smart_9_raw": "power_on_hours",
    "smart_194_raw": "temperature_c",
}
FEATURES = list(FEATURE_COLUMNS.values())
UNITS = {f: "count" for f in FEATURES} | {"power_on_hours": "h", "temperature_c": "C"}
TARGET = f"fails_within_{HORIZON_DAYS}d"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def keep_negative_drive(serial: str) -> bool:
    return int(hashlib.md5(serial.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF < NEG_DRIVE_RATE


def _members(zf: zipfile.ZipFile) -> list[str]:
    return sorted(n for n in zf.namelist() if n.endswith(".csv") and "__MACOSX" not in n)


def build(zip_path: Path) -> pd.DataFrame:
    """Return sampled drive-day rows with features, label, weight, serial and day index."""
    with zipfile.ZipFile(zip_path) as zf:
        days = _members(zf)
        # Pass 1: failure day per drive (cheap columns only).
        fail_day: dict[str, int] = {}
        for i, name in enumerate(days):
            with zf.open(name) as fh:
                d = pd.read_csv(fh, usecols=["serial_number", "failure"])
            for s in d.loc[d["failure"] == 1, "serial_number"]:
                fail_day.setdefault(s, i)
        last_obs = len(days) - HORIZON_DAYS
        frames = []
        # Pass 2: features on sampled observation days.
        for i in range(0, last_obs, DAY_STRIDE):
            with zf.open(days[i]) as fh:
                d = pd.read_csv(fh, usecols=["serial_number", "model", *FEATURE_COLUMNS])
            failing = d["serial_number"].isin(fail_day)
            keep = failing | d["serial_number"].map(keep_negative_drive)
            d = d[keep].copy()
            d["day"] = i
            frames.append(d)
    df = pd.concat(frames, ignore_index=True).rename(columns=FEATURE_COLUMNS)
    f = df["serial_number"].map(fail_day)
    df[TARGET] = ((f - df["day"] >= 0) & (f - df["day"] < HORIZON_DAYS)).astype(int)
    df["drive_failed_in_quarter"] = f.notna().astype(int)
    # Undo negative-drive sampling at evaluation time.
    df["weight"] = np.where(df["drive_failed_in_quarter"] == 1, 1.0, 1.0 / NEG_DRIVE_RATE)
    return df


def summary(df: pd.DataFrame) -> dict:
    return {
        "rows": int(len(df)),
        "drives": int(df["serial_number"].nunique()),
        "failed_drives": int(df.loc[df["drive_failed_in_quarter"] == 1, "serial_number"].nunique()),
        "positive_rows": int(df[TARGET].sum()),
        "horizon_days": HORIZON_DAYS,
        "neg_drive_rate": NEG_DRIVE_RATE,
        "day_stride": DAY_STRIDE,
        "missing_fraction": {c: round(float(df[c].isna().mean()), 4) for c in FEATURES},
    }
