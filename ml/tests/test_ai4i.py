import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

ML = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML))

from infraguard_ml import ai4i, train_industrial  # noqa: E402

REAL_CSV = ML.parent / "data" / "raw" / "ai4i" / ai4i.CSV_NAME


def tiny_frame(n: int = 600, seed: int = 0) -> pd.DataFrame:
    """Small made-up frame with the AI4I schema. Test fixture only; not real data."""
    rng = np.random.default_rng(seed)
    torque = rng.normal(40, 10, n)
    wear = rng.integers(0, 250, n)
    fail = ((torque > 55) | (wear > 220)).astype(int)
    return pd.DataFrame(
        {
            "UDI": np.arange(1, n + 1),
            "Product ID": [f"X{i}" for i in range(n)],
            "Type": rng.choice(ai4i.TYPE_VALUES, n),
            "Air temperature [K]": rng.normal(300, 2, n).round(1),
            "Process temperature [K]": rng.normal(310, 1.5, n).round(1),
            "Rotational speed [rpm]": rng.integers(1200, 2800, n),
            "Torque [Nm]": torque.round(1),
            "Tool wear [min]": wear,
            "Machine failure": fail,
            "TWF": (wear > 220).astype(int),
            "HDF": 0,
            "PWF": (torque > 55).astype(int),
            "OSF": 0,
            "RNF": 0,
        }
    )


@pytest.fixture
def tiny_csv(tmp_path) -> Path:
    p = tmp_path / "ai4i_tiny.csv"
    tiny_frame().to_csv(p, index=False, encoding="utf-8-sig")
    return p


def test_features_exclude_target_modes_and_ids():
    X, y = ai4i.features_and_target(tiny_frame())
    assert list(X.columns) == ai4i.FEATURES
    assert not set(X.columns) & {"machine_failure", "twf", "hdf", "pwf", "osf", "rnf", "udi", "product_id"}
    assert not set(X.columns) & set(ai4i.EXCLUDED_COLUMNS)
    assert y.name == ai4i.TARGET_COLUMN


def test_schema_rejects_bad_input():
    df = tiny_frame()
    with pytest.raises(ai4i.SchemaError):
        ai4i.validate_raw(df.drop(columns=["TWF"]))
    bad = df.copy()
    bad.loc[0, "Type"] = "Z"
    with pytest.raises(ai4i.SchemaError):
        ai4i.validate_raw(bad)
    dup = df.copy()
    dup.loc[1, "UDI"] = dup.loc[0, "UDI"]
    with pytest.raises(ai4i.SchemaError):
        ai4i.validate_raw(dup)


def test_split_is_reproducible_and_disjoint():
    X, y = ai4i.features_and_target(tiny_frame())
    a = train_industrial.split(X, y, 42)
    b = train_industrial.split(X, y, 42)
    for p, q in zip(a, b):
        assert np.array_equal(p, q)
    tr, va, te = map(set, a)
    assert not (tr & va or tr & te or va & te)
    assert len(tr | va | te) == len(X)


def test_preprocessing_fit_on_train_only():
    X, y = ai4i.features_and_target(tiny_frame())
    tr, _, _ = train_industrial.split(X, y, 42)
    pipe = train_industrial.candidates(42)["logreg_C1.0"].fit(X.iloc[tr], y.iloc[tr])
    scaler = pipe.named_steps["prep"].named_transformers_["num"]
    assert np.allclose(scaler.mean_, X.iloc[tr][ai4i.NUMERIC].mean().values)


def test_tiny_fixture_end_to_end(tiny_csv, tmp_path):
    out = tmp_path / "artifacts"
    m = train_industrial.train(tiny_csv, out, plots=False)
    c = m["contract_metrics"]
    assert c["split"] == "test" and c["n"] == 120
    assert 0 <= m["risk_thresholds"]["medium"] < m["risk_thresholds"]["high"]
    assert set(m["error_examples_test"]) == {"false_negatives", "false_positives"}

    model = joblib.load(out / "ai4i" / "pipeline.joblib")
    row = pd.DataFrame([{"type": "M", "air_temperature_k": 298.9, "process_temperature_k": 309.1,
                         "rotational_speed_rpm": 1410, "torque_nm": 65.7, "tool_wear_min": 191}])
    proba = model.predict_proba(row[ai4i.FEATURES])
    assert proba.shape == (1, 2) and 0 <= proba[0, 1] <= 1

    schema = json.loads((out / "ai4i" / "feature_schema.json").read_text())
    assert schema["features"] == ai4i.FEATURES
    splits = json.loads((out / "ai4i" / "splits.json").read_text())
    assert not set(splits["train"]) & set(splits["test"])


def test_unknown_type_is_refused(tiny_csv, tmp_path):
    train_industrial.train(tiny_csv, tmp_path / "a", plots=False)
    model = joblib.load(tmp_path / "a" / "ai4i" / "pipeline.joblib")
    row = pd.DataFrame([{"type": "Q", "air_temperature_k": 298.9, "process_temperature_k": 309.1,
                         "rotational_speed_rpm": 1410, "torque_nm": 65.7, "tool_wear_min": 191}])
    with pytest.raises(ValueError):
        model.predict_proba(row)


@pytest.mark.skipif(not REAL_CSV.is_file(), reason="run scripts/prepare_ai4i.py first")
def test_real_data_schema_and_checksum():
    assert ai4i.sha256(REAL_CSV) == ai4i.CSV_SHA256
    s = ai4i.summary(ai4i.load_raw(REAL_CSV))
    assert s["rows"] == 10000


def test_committed_metrics_match_contract_schema():
    path = ML / "artifacts" / "metrics" / f"{train_industrial.DETECTOR_ID}.json"
    if not path.is_file():
        pytest.skip("model not trained")
    sys.path.insert(0, str(ML.parent))
    from backend.app.schemas.models import ModelMetrics

    ModelMetrics.model_validate(json.loads(path.read_text())["contract_metrics"])
