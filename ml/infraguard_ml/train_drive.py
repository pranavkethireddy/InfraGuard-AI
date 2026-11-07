"""Train and evaluate drive-failure-v1: will this hard drive fail within 30 days?

Flow: drive-grouped 60/20/20 split (a drive is in exactly one split) -> candidates fit on
train -> select on validation PR-AUC -> thresholds on validation -> frozen model scored on
test once. Negative drives were subsampled, so every metric below is computed with
sample weights that restore the real fleet mix. Nothing is written by hand.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from . import backblaze as bb

DETECTOR_ID = "drive-failure-v1"
MODEL_VERSION = "0.1.0"
SEED = 42
THRESHOLD_SELECTION = "max F1 on validation split (fleet-reweighted)"
MEDIUM_SELECTION = "max F2 on validation split (fleet-reweighted), below the high threshold"


def r4(x):
    return None if x is None else round(float(x), 4)


def candidates(seed: int) -> dict[str, Pipeline]:
    out: dict[str, Pipeline] = {}
    for c in (0.1, 1.0):
        prep = ColumnTransformer(
            [("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("log", FunctionTransformer(np.log1p)),
                               ("sc", StandardScaler())]), bb.FEATURES)]
        )
        out[f"logreg_C{c}"] = Pipeline([("prep", prep), ("clf", LogisticRegression(C=c, max_iter=2000))])
    for lr in (0.05, 0.1):
        for leaves in (15, 31):
            out[f"hgb_lr{lr}_leaves{leaves}"] = Pipeline(
                [("prep", ColumnTransformer([("num", "passthrough", bb.FEATURES)])),
                 ("clf", HistGradientBoostingClassifier(learning_rate=lr, max_leaf_nodes=leaves, random_state=seed))]
            )
    return out


def split(df: pd.DataFrame, seed: int):
    drives = df.groupby("serial_number")["drive_failed_in_quarter"].max()
    tr, rest = train_test_split(drives.index, test_size=0.4, stratify=drives.values, random_state=seed)
    va, te = train_test_split(rest, test_size=0.5, stratify=drives.loc[rest].values, random_state=seed)
    s = df["serial_number"]
    return np.flatnonzero(s.isin(tr)), np.flatnonzero(s.isin(va)), np.flatnonzero(s.isin(te))


def best_threshold(y, s, w, beta: float) -> float:
    p, r, t = precision_recall_curve(y, s, sample_weight=w)
    with np.errstate(divide="ignore", invalid="ignore"):
        f = np.nan_to_num((1 + beta**2) * p[:-1] * r[:-1] / (beta**2 * p[:-1] + r[:-1]))
    return float(t[int(np.argmax(f))])


def at_threshold(y, s, w, thr: float) -> dict:
    pred = s >= thr
    tp, fp = w[pred & (y == 1)].sum(), w[pred & (y == 0)].sum()
    fn, tn = w[~pred & (y == 1)].sum(), w[~pred & (y == 0)].sum()
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {
        "precision": prec, "recall": rec, "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0,
        "confusion_matrix": {k: int(round(v)) for k, v in {"tp": tp, "fp": fp, "tn": tn, "fn": fn}.items()},
        "false_alert_rate": fp / (fp + tn) if fp + tn else None,
    }


def train(df: pd.DataFrame, zip_path: Path | None, artifacts_root: Path, seed: int = SEED) -> dict:
    root = Path(artifacts_root)
    X, y, w = df[bb.FEATURES], df[bb.TARGET].to_numpy(), df["weight"].to_numpy()
    tr, va, te = split(df, seed)
    sd = df["serial_number"]
    assert not (set(sd.iloc[tr]) & set(sd.iloc[va]) or set(sd.iloc[tr]) & set(sd.iloc[te]) or set(sd.iloc[va]) & set(sd.iloc[te]))

    val, fitted = {}, {}
    for name, pipe in candidates(seed).items():
        m = clone(pipe).fit(X.iloc[tr], y[tr], clf__sample_weight=w[tr])
        s = m.predict_proba(X.iloc[va])[:, 1]
        val[name] = {"pr_auc": r4(average_precision_score(y[va], s, sample_weight=w[va]))}
        fitted[name] = m
    chosen = max(val, key=lambda k: val[k]["pr_auc"])
    model = fitted[chosen]

    s_va = model.predict_proba(X.iloc[va])[:, 1]
    high = best_threshold(y[va], s_va, w[va], 1.0)
    medium = best_threshold(y[va], s_va, w[va], 2.0)
    if medium >= high:
        medium = high / 2

    s_te = model.predict_proba(X.iloc[te])[:, 1]
    test = at_threshold(y[te], s_te, w[te], high)
    test_medium = at_threshold(y[te], s_te, w[te], medium)
    prevalence = float((w[te] * y[te]).sum() / w[te].sum())

    contract_metrics = {
        "split": "test",
        "evaluated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "dataset_version": bb.DATASET_VERSION,
        "seed": seed,
        "n": int(len(te)),
        "positives": int(y[te].sum()),
        "threshold": r4(high),
        "threshold_selection": THRESHOLD_SELECTION,
        "precision": r4(test["precision"]),
        "recall": r4(test["recall"]),
        "f1": r4(test["f1"]),
        "pr_auc": r4(average_precision_score(y[te], s_te, sample_weight=w[te])),
        "roc_auc": r4(roc_auc_score(y[te], s_te, sample_weight=w[te])),
        "brier": None,
        "calibrated": False,
        "confusion_matrix": test["confusion_matrix"],
        "baseline": {"name": "fleet prevalence (no-skill)", "pr_auc": r4(prevalence), "f1": None},
        "metrics_file": f"ml/artifacts/metrics/{DETECTOR_ID}.json",
    }
    metrics = {
        "detector_id": DETECTOR_ID,
        "model_version": MODEL_VERSION,
        "chosen_candidate": chosen,
        "target": f"Backblaze drive records failure within {bb.HORIZON_DAYS} days of the observation day",
        "prediction_horizon_hours": bb.HORIZON_DAYS * 24,
        "score_kind": "model_score",
        "contract_metrics": contract_metrics,
        "risk_thresholds": {"medium": r4(medium), "high": r4(high)},
        "medium_threshold_selection": MEDIUM_SELECTION,
        "test_at_medium_threshold": {k: (r4(v) if isinstance(v, float) else v) for k, v in test_medium.items()},
        "test_false_alert_rate": r4(test["false_alert_rate"]),
        "evaluation_note": (
            "Non-failing drives were sampled at neg_drive_rate; metrics and confusion-matrix counts are "
            "reweighted by 1/neg_drive_rate to estimate the real fleet. n and positives are sampled row counts."
        ),
        "validation_candidates": val,
        "splits": {
            "method": "split by drive serial_number, stratified by 'failed in quarter', 60/20/20, fixed seed",
            "train_rows": int(len(tr)), "validation_rows": int(len(va)), "test_rows": int(len(te)),
            "disjoint_drives": True,
        },
        "data": {"source": bb.SOURCE_URL, "zip_sha256": bb.ZIP_SHA256 if zip_path else None,
                 "license": bb.LICENSE, **bb.summary(df)},
        "features": bb.FEATURES,
        "units": bb.UNITS,
    }
    schema = {
        "detector_id": DETECTOR_ID, "model_version": MODEL_VERSION, "features": bb.FEATURES, "units": bb.UNITS,
        "missing_allowed": True, "risk_thresholds": metrics["risk_thresholds"],
        "prediction_horizon_hours": bb.HORIZON_DAYS * 24, "sklearn_version": __import__("sklearn").__version__,
    }
    for sub in ("backblaze", "metrics", "model_cards"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    joblib.dump(model, root / "backblaze" / "pipeline.joblib")
    (root / "backblaze" / "feature_schema.json").write_text(json.dumps(schema, indent=2) + "\n")
    (root / "metrics" / f"{DETECTOR_ID}.json").write_text(json.dumps(metrics, indent=2) + "\n")
    (root / "model_cards" / f"{DETECTOR_ID}.md").write_text(model_card(metrics))
    return metrics


def model_card(m: dict) -> str:
    c, d = m["contract_metrics"], m["data"]
    return f"""# Model card: {m['detector_id']} ({m['model_version']})

Generated by `scripts/train_drive.py`. Every number below is computed by the training script.

- **Task:** {m['target']}. Horizon {m['prediction_horizon_hours']} h.
- **Data:** real Backblaze data-center hard drives, {d['source']} ({m['data']['license']}).
  {d['rows']} sampled drive-days, {d['drives']} drives, {d['failed_drives']} failed in the quarter.
- **Features:** {', '.join(m['features'])} (SMART raw values; missing values allowed).
- **Model:** {m['chosen_candidate']}, chosen on validation PR-AUC.
- **Split:** {m['splits']['method']}.

## Held-out test (fleet-reweighted)

| Metric | Value |
|---|---|
| PR-AUC | {c['pr_auc']} (no-skill {c['baseline']['pr_auc']}) |
| ROC-AUC | {c['roc_auc']} |
| Precision @ high | {c['precision']} |
| Recall @ high | {c['recall']} |
| F1 @ high | {c['f1']} |
| High threshold | {c['threshold']} |
| Medium threshold | {m['risk_thresholds']['medium']} |

{m['evaluation_note']}

## Limitations

- One quarter of one fleet (Backblaze, Q1 2025); other vendors, workloads and SMART encodings may differ.
- Scores are not calibrated probabilities.
- Sudden failures with no SMART warning cannot be predicted from these features.
"""
