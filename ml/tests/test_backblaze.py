import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ML = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ML))

from infraguard_ml import backblaze as bb, train_drive  # noqa: E402

DAYS = 40


def fake_zip(path: Path) -> Path:
    """Made-up drive days in the Backblaze layout. Test fixture only; not real data."""
    rng = np.random.default_rng(0)
    healthy = [f"H{i}" for i in range(3000)]
    with zipfile.ZipFile(path, "w") as zf:
        for d in range(DAYS):
            rows = [{"serial_number": s, "model": "M", "failure": 0} for s in healthy]
            if d <= 20:
                rows.append({"serial_number": "F20", "model": "M", "failure": int(d == 20)})
            if d <= 35:
                rows.append({"serial_number": "F35", "model": "M", "failure": int(d == 35)})
            df = pd.DataFrame(rows)
            for c in bb.FEATURE_COLUMNS:
                df[c] = rng.integers(0, 5, len(df))
            buf = io.StringIO()
            df.to_csv(buf, index=False)
            zf.writestr(f"data/2025-01-{d + 1:02d}.csv", buf.getvalue())
    return path


def test_labels_use_only_future_failure_within_horizon(tmp_path):
    df = bb.build(fake_zip(tmp_path / "f.zip"))
    assert df["day"].max() < DAYS - bb.HORIZON_DAYS  # every label fully observed
    f20 = df[df.serial_number == "F20"].set_index("day")[bb.TARGET]
    assert f20.loc[0] == 1  # 20 days before failure -> positive
    f35 = df[df.serial_number == "F35"].set_index("day")[bb.TARGET]
    assert f35.loc[4] == 0 and f35.loc[6] == 1  # 31 days before -> 0, 29 days before -> 1
    assert (df.loc[df.serial_number.str.startswith("H"), bb.TARGET] == 0).all()


def test_negative_drives_sampled_and_reweighted(tmp_path):
    df = bb.build(fake_zip(tmp_path / "f.zip"))
    h = df[df.serial_number.str.startswith("H")]
    assert 0 < h.serial_number.nunique() < 3000 * 0.05
    assert (h["weight"] == 1 / bb.NEG_DRIVE_RATE).all()
    assert (df.loc[df.drive_failed_in_quarter == 1, "weight"] == 1).all()


def test_split_keeps_each_drive_in_one_split():
    rng = np.random.default_rng(1)
    df = pd.DataFrame({"serial_number": np.repeat([f"S{i}" for i in range(200)], 5),
                       "drive_failed_in_quarter": np.repeat(rng.integers(0, 2, 200), 5)})
    tr, va, te = train_drive.split(df, 42)
    sets = [set(df.serial_number.iloc[i]) for i in (tr, va, te)]
    assert not (sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2])
    assert len(tr) + len(va) + len(te) == len(df)


def test_committed_metrics_match_contract_schema():
    path = ML / "artifacts" / "metrics" / f"{train_drive.DETECTOR_ID}.json"
    if not path.is_file():
        import pytest

        pytest.skip("model not trained")
    import json

    sys.path.insert(0, str(ML.parent))
    from backend.app.schemas.models import ModelMetrics

    raw = json.loads(path.read_text())
    ModelMetrics.model_validate(raw["contract_metrics"])
    assert raw["prediction_horizon_hours"] == 720
