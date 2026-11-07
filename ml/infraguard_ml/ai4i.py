"""AI4I 2020 loading, schema checks and feature selection for industrial-failure-v1.

AI4I is a synthetic manufacturing-machine benchmark. The target is "Machine failure"
at the time of observation; it is not a forecast.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

SOURCE_URL = "https://archive.ics.uci.edu/static/public/601/ai4i+2020+predictive+maintenance+dataset.zip"
CSV_NAME = "ai4i2020.csv"
CSV_SHA256 = "dc6630cd9b1f0f853922fad78a1b6436570d3f1ec863f1dd5c4340ac56bc8a8e"
DATASET_VERSION = "UCI AI4I 2020 (id 601)"
LICENSE = "CC BY 4.0"

# Raw column -> contract field name (contracts/fixtures/prediction.industrial.request.json).
FEATURE_COLUMNS = {
    "Type": "type",
    "Air temperature [K]": "air_temperature_k",
    "Process temperature [K]": "process_temperature_k",
    "Rotational speed [rpm]": "rotational_speed_rpm",
    "Torque [Nm]": "torque_nm",
    "Tool wear [min]": "tool_wear_min",
}
CATEGORICAL = ["type"]
NUMERIC = [v for v in FEATURE_COLUMNS.values() if v not in CATEGORICAL]
FEATURES = CATEGORICAL + NUMERIC
TYPE_VALUES = ["H", "L", "M"]

TARGET_COLUMN = "Machine failure"
# Target, failure-mode labels (derived from the outcome) and identifiers. Never model inputs.
EXCLUDED_COLUMNS = ["Machine failure", "TWF", "HDF", "PWF", "OSF", "RNF", "UDI", "Product ID"]
EXPECTED_COLUMNS = ["UDI", "Product ID", *FEATURE_COLUMNS, "Machine failure", "TWF", "HDF", "PWF", "OSF", "RNF"]


class SchemaError(ValueError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_raw(path: Path) -> pd.DataFrame:
    """Read the CSV (it starts with a UTF-8 BOM) and check schema and basic quality."""
    df = pd.read_csv(path, encoding="utf-8-sig")
    validate_raw(df)
    return df


def validate_raw(df: pd.DataFrame) -> None:
    if list(df.columns) != EXPECTED_COLUMNS:
        raise SchemaError(f"unexpected columns: {list(df.columns)}")
    if df["UDI"].duplicated().any():
        raise SchemaError("duplicate UDI values")
    if df[EXPECTED_COLUMNS].isna().any().any():
        raise SchemaError("missing values present")
    unknown = set(df["Type"]) - set(TYPE_VALUES)
    if unknown:
        raise SchemaError(f"unknown Type values: {sorted(unknown)}")
    if not set(df[TARGET_COLUMN].unique()) <= {0, 1}:
        raise SchemaError("target is not binary")


def features_and_target(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Select only the six safe inputs, renamed to contract field names."""
    X = df[list(FEATURE_COLUMNS)].rename(columns=FEATURE_COLUMNS)[FEATURES]
    y = df[TARGET_COLUMN].astype(int)
    return X, y


def summary(df: pd.DataFrame) -> dict:
    """Counts used in the dataset manifest and metrics file."""
    return {
        "rows": int(len(df)),
        "positives": int(df[TARGET_COLUMN].sum()),
        "positive_rate": round(float(df[TARGET_COLUMN].mean()), 4),
        "failure_modes": {m: int(df[m].sum()) for m in ["TWF", "HDF", "PWF", "OSF", "RNF"]},
        "type_counts": {k: int(v) for k, v in df["Type"].value_counts().sort_index().items()},
        "failures_by_type": {k: int(v) for k, v in df.groupby("Type")[TARGET_COLUMN].sum().sort_index().items()},
        "duplicate_feature_rows": int(df[list(FEATURE_COLUMNS)].duplicated().sum()),
    }
