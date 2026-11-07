"""Train and evaluate industrial-failure-v1 on AI4I (SKILL.md Phase C and Phase J).

Flow: stratified 60/20/20 split -> candidates fit on train -> select on validation PR-AUC
-> thresholds chosen on validation -> frozen model scored on test once -> artifacts.
Every number in the outputs is computed here; nothing is written by hand.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from . import ai4i

DETECTOR_ID = "industrial-failure-v1"
MODEL_VERSION = "0.1.0"
SEED = 42
THRESHOLD_SELECTION = "max F1 on validation split"
MEDIUM_SELECTION = "max F2 (recall-weighted) on validation split, below the high threshold"


@dataclass
class Paths:
    root: Path  # ml/artifacts

    @property
    def pipeline(self) -> Path:
        return self.root / "ai4i" / "pipeline.joblib"

    @property
    def feature_schema(self) -> Path:
        return self.root / "ai4i" / "feature_schema.json"

    @property
    def splits(self) -> Path:
        return self.root / "ai4i" / "splits.json"

    @property
    def metrics(self) -> Path:
        return self.root / "metrics" / f"{DETECTOR_ID}.json"

    @property
    def model_card(self) -> Path:
        return self.root / "model_cards" / f"{DETECTOR_ID}.md"

    @property
    def plots(self) -> Path:
        return self.root / "plots"


def preprocessor(scale: bool) -> ColumnTransformer:
    numeric = StandardScaler() if scale else "passthrough"
    return ColumnTransformer(
        [
            ("type", OneHotEncoder(categories=[ai4i.TYPE_VALUES], handle_unknown="error"), ai4i.CATEGORICAL),
            ("num", numeric, ai4i.NUMERIC),
        ]
    )


def candidates(seed: int) -> dict[str, Pipeline]:
    """Modest grid. Each entry is fit on train only and compared on validation."""
    out: dict[str, Pipeline] = {
        "dummy_prior": Pipeline([("prep", preprocessor(False)), ("clf", DummyClassifier(strategy="prior"))]),
    }
    for c in (0.1, 1.0, 10.0):
        out[f"logreg_C{c}"] = Pipeline(
            [
                ("prep", preprocessor(True)),
                ("clf", LogisticRegression(C=c, class_weight="balanced", max_iter=5000)),
            ]
        )
    for lr in (0.05, 0.1):
        for leaves in (15, 31):
            out[f"hgb_lr{lr}_leaves{leaves}"] = Pipeline(
                [
                    ("prep", preprocessor(False)),
                    (
                        "clf",
                        HistGradientBoostingClassifier(
                            learning_rate=lr, max_leaf_nodes=leaves, max_iter=300, random_state=seed
                        ),
                    ),
                ]
            )
    return out


def split(X: pd.DataFrame, y: pd.Series, seed: int):
    idx = np.arange(len(X))
    train_idx, rest = train_test_split(idx, test_size=0.4, stratify=y, random_state=seed)
    val_idx, test_idx = train_test_split(rest, test_size=0.5, stratify=y.iloc[rest], random_state=seed)
    return train_idx, val_idx, test_idx


def best_threshold(y_true, scores, beta: float) -> float:
    precision, recall, thresholds = precision_recall_curve(y_true, scores)
    p, r = precision[:-1], recall[:-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        f = (1 + beta**2) * p * r / (beta**2 * p + r)
    f = np.nan_to_num(f)
    return float(thresholds[int(np.argmax(f))])


def score(model: Pipeline, X: pd.DataFrame) -> np.ndarray:
    return model.predict_proba(X)[:, 1]


def threshold_metrics(y_true, scores, threshold: float) -> dict:
    pred = (scores >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
    return {
        "precision": float(precision_score(y_true, pred, zero_division=0)),
        "recall": float(recall_score(y_true, pred, zero_division=0)),
        "f1": float(f1_score(y_true, pred, zero_division=0)),
        "confusion_matrix": {"tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn)},
        "alerts": int(pred.sum()),
        "false_alert_rate": float(fp / (fp + tn)) if (fp + tn) else None,
    }


def r4(x):
    return None if x is None else round(float(x), 4)


def train(csv_path: Path, artifacts_root: Path, seed: int = SEED, plots: bool = True) -> dict:
    paths = Paths(Path(artifacts_root))
    df = ai4i.load_raw(csv_path)
    X, y = ai4i.features_and_target(df)
    leaked = set(X.columns) & set(ai4i.EXCLUDED_COLUMNS)
    assert not leaked, f"excluded columns in features: {leaked}"

    train_idx, val_idx, test_idx = split(X, y, seed)
    assert not (set(train_idx) & set(val_idx) or set(train_idx) & set(test_idx) or set(val_idx) & set(test_idx))
    X_tr, y_tr = X.iloc[train_idx], y.iloc[train_idx]
    X_va, y_va = X.iloc[val_idx], y.iloc[val_idx]
    X_te, y_te = X.iloc[test_idx], y.iloc[test_idx]

    # 1. Fit every candidate on train; compare on validation only.
    val_results: dict[str, dict] = {}
    fitted: dict[str, Pipeline] = {}
    for name, pipe in candidates(seed).items():
        model = clone(pipe).fit(X_tr, y_tr)
        s = score(model, X_va)
        thr = best_threshold(y_va, s, beta=1.0)
        val_results[name] = {"pr_auc": average_precision_score(y_va, s), **threshold_metrics(y_va, s, thr), "threshold": thr}
        fitted[name] = model
    trained = {k: v for k, v in val_results.items() if k != "dummy_prior"}
    chosen = max(trained, key=lambda k: trained[k]["pr_auc"])
    model = fitted[chosen]

    # 2. Operating thresholds from validation scores of the frozen chosen model.
    s_va = score(model, X_va)
    high = best_threshold(y_va, s_va, beta=1.0)
    medium = best_threshold(y_va, s_va, beta=2.0)
    if medium >= high:
        medium = high / 2

    # 3. Single test evaluation of the frozen model and the baseline.
    s_te = score(model, X_te)
    test = threshold_metrics(y_te, s_te, high)
    test_medium = threshold_metrics(y_te, s_te, medium)
    s_te_base = score(fitted["dummy_prior"], X_te)
    base = threshold_metrics(y_te, s_te_base, 0.5)
    evaluated_at = datetime.now(UTC).replace(microsecond=0)

    imp = permutation_importance(model, X_va, y_va, scoring="average_precision", n_repeats=10, random_state=seed)
    importance = {f: r4(m) for f, m in sorted(zip(X.columns, imp.importances_mean), key=lambda t: -t[1])}

    test_frame = df.iloc[test_idx][["UDI", *ai4i.FEATURE_COLUMNS, "TWF", "HDF", "PWF", "OSF", "RNF"]].copy()
    test_frame["score"] = s_te
    test_frame["label"] = y_te.values
    fn_rows = test_frame[(test_frame.label == 1) & (test_frame.score < high)].sort_values("score").head(5)
    fp_rows = test_frame[(test_frame.label == 0) & (test_frame.score >= high)].sort_values("score", ascending=False).head(5)

    def rows(frame):
        return json.loads(frame.round(4).to_json(orient="records"))

    contract_metrics = {
        "split": "test",
        "evaluated_at": evaluated_at.isoformat().replace("+00:00", "Z"),
        "dataset_version": ai4i.DATASET_VERSION,
        "seed": seed,
        "n": int(len(test_idx)),
        "positives": int(y_te.sum()),
        "threshold": r4(high),
        "threshold_selection": THRESHOLD_SELECTION,
        "precision": r4(test["precision"]),
        "recall": r4(test["recall"]),
        "f1": r4(test["f1"]),
        "pr_auc": r4(average_precision_score(y_te, s_te)),
        "roc_auc": r4(roc_auc_score(y_te, s_te)),
        "brier": r4(brier_score_loss(y_te, s_te)),
        "calibrated": False,
        "confusion_matrix": test["confusion_matrix"],
        "baseline": {
            "name": "dummy_prior (majority/prevalence)",
            "pr_auc": r4(average_precision_score(y_te, s_te_base)),
            "f1": r4(base["f1"]),
        },
        "metrics_file": f"ml/artifacts/metrics/{DETECTOR_ID}.json",
    }

    ranges = {c: {"min": r4(X_tr[c].min()), "max": r4(X_tr[c].max())} for c in ai4i.NUMERIC}
    metrics = {
        "detector_id": DETECTOR_ID,
        "model_version": MODEL_VERSION,
        "chosen_candidate": chosen,
        "target": "AI4I 'Machine failure' at time of observation (not a forecast)",
        "score_kind": "model_score",
        "contract_metrics": contract_metrics,
        "risk_thresholds": {"medium": r4(medium), "high": r4(high)},
        "medium_threshold_selection": MEDIUM_SELECTION,
        "test_at_medium_threshold": {k: (r4(v) if isinstance(v, float) else v) for k, v in test_medium.items()},
        "test_false_alert_rate": r4(test["false_alert_rate"]),
        "beats_baseline_on_test_pr_auc": contract_metrics["pr_auc"] > contract_metrics["baseline"]["pr_auc"],
        "validation_candidates": {
            name: {m: (r4(v) if isinstance(v, float) else v) for m, v in res.items()}
            for name, res in val_results.items()
        },
        "splits": {
            "method": "stratified random 60/20/20 on Machine failure, fixed seed",
            "train": {"n": int(len(train_idx)), "positives": int(y_tr.sum())},
            "validation": {"n": int(len(val_idx)), "positives": int(y_va.sum())},
            "test": {"n": int(len(test_idx)), "positives": int(y_te.sum())},
            "disjoint": True,
            "caveat": "Random split of a synthetic cross-sectional benchmark; no time or machine grouping exists.",
        },
        "data": {
            "source": ai4i.SOURCE_URL,
            "csv_sha256": ai4i.sha256(csv_path),
            "license": ai4i.LICENSE,
            **ai4i.summary(df),
        },
        "features": ai4i.FEATURES,
        "excluded_columns": ai4i.EXCLUDED_COLUMNS,
        "permutation_importance_validation_pr_auc": importance,
        "error_examples_test": {"false_negatives": rows(fn_rows), "false_positives": rows(fp_rows)},
        "calibration": "not calibrated; scores are model scores, not probabilities",
    }

    feature_schema = {
        "detector_id": DETECTOR_ID,
        "model_version": MODEL_VERSION,
        "features": ai4i.FEATURES,
        "categorical": {"type": ai4i.TYPE_VALUES},
        "units": {
            "air_temperature_k": "K",
            "process_temperature_k": "K",
            "rotational_speed_rpm": "rpm",
            "torque_nm": "Nm",
            "tool_wear_min": "min",
        },
        "training_ranges": ranges,
        "risk_thresholds": metrics["risk_thresholds"],
        "sklearn_version": __import__("sklearn").__version__,
    }

    for p in (paths.pipeline, paths.metrics, paths.model_card):
        p.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, paths.pipeline)
    paths.feature_schema.write_text(json.dumps(feature_schema, indent=2) + "\n")
    paths.splits.write_text(
        json.dumps(
            {
                "seed": seed,
                "key": "UDI",
                "train": sorted(df["UDI"].iloc[train_idx].tolist()),
                "validation": sorted(df["UDI"].iloc[val_idx].tolist()),
                "test": sorted(df["UDI"].iloc[test_idx].tolist()),
            }
        )
        + "\n"
    )
    paths.metrics.write_text(json.dumps(metrics, indent=2) + "\n")
    paths.model_card.write_text(model_card(metrics))
    if plots:
        write_plots(paths.plots, y_te, s_te, test["confusion_matrix"], high)
    return metrics


def write_plots(out: Path, y_true, scores, cm: dict, threshold: float) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out.mkdir(parents=True, exist_ok=True)
    precision, recall, _ = precision_recall_curve(y_true, scores)
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.plot(recall, precision)
    ax.axhline(float(np.mean(y_true)), linestyle="--", label="baseline (prevalence)")
    ax.set(xlabel="Recall", ylabel="Precision", title=f"{DETECTOR_ID} test PR curve")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / f"{DETECTOR_ID}_pr_curve.png", dpi=120)
    plt.close(fig)

    grid = np.array([[cm["tn"], cm["fp"]], [cm["fn"], cm["tp"]]])
    fig, ax = plt.subplots(figsize=(4, 4))
    ax.imshow(grid, cmap="Blues")
    for (i, j), v in np.ndenumerate(grid):
        ax.text(j, i, str(v), ha="center", va="center")
    ax.set(
        xticks=[0, 1], yticks=[0, 1], xticklabels=["pred 0", "pred 1"], yticklabels=["true 0", "true 1"],
        title=f"Test confusion @ {threshold:.3f}",
    )
    fig.tight_layout()
    fig.savefig(out / f"{DETECTOR_ID}_confusion.png", dpi=120)
    plt.close(fig)


def model_card(m: dict) -> str:
    c = m["contract_metrics"]
    s = m["splits"]
    d = m["data"]
    imp = ", ".join(f"{k} ({v})" for k, v in m["permutation_importance_validation_pr_auc"].items())
    return f"""# Model card: {DETECTOR_ID}

Generated by `scripts/train_industrial.py`. Do not edit numbers by hand.

## Intended use
Demonstration of a complete, honestly evaluated failure-classification workflow in InfraGuard AI.

**Domain restriction:** synthetic manufacturing-machine benchmark; not validated for facility operations.

## Prohibited uses
- Scoring cooling units, UPS, drives, HVAC or any equipment other than AI4I-style milling machines.
- Presenting the score as a calibrated probability or a real-world risk.
- Presenting the output as a forecast. There is no prediction horizon.

## Source
{ai4i.DATASET_VERSION}, {d['license']}. {d['rows']} synthetic rows. CSV SHA-256 `{d['csv_sha256']}`.

## Target and horizon
`Machine failure` at the time of the observation. Horizon: none.

## Inputs
{', '.join(m['features'])}. Excluded: {', '.join(m['excluded_columns'])}.

## Data
Positives: {d['positives']} of {d['rows']} ({d['positive_rate']}). Failure modes: {d['failure_modes']}.
Type counts: {d['type_counts']}; failures by type: {d['failures_by_type']}.

Split: {s['method']}. Train {s['train']['n']} ({s['train']['positives']} pos), validation {s['validation']['n']} ({s['validation']['positives']} pos), test {s['test']['n']} ({s['test']['positives']} pos).
Caveat: {s['caveat']}

## Model
Chosen candidate: `{m['chosen_candidate']}` (highest validation PR-AUC among trained candidates).

## Held-out test results (evaluated once)
| Metric | Model | Baseline ({c['baseline']['name']}) |
|---|---|---|
| PR-AUC | {c['pr_auc']} | {c['baseline']['pr_auc']} |
| F1 @ threshold | {c['f1']} | {c['baseline']['f1']} |
| Precision | {c['precision']} | |
| Recall | {c['recall']} | |
| ROC-AUC | {c['roc_auc']} | |
| Brier (uncalibrated) | {c['brier']} | |

Threshold {c['threshold']} ({c['threshold_selection']}). Confusion matrix: {c['confusion_matrix']}. False-alert rate: {m['test_false_alert_rate']}.

Risk levels: medium >= {m['risk_thresholds']['medium']} ({m['medium_threshold_selection']}), high >= {m['risk_thresholds']['high']}.
At the medium threshold on test: {m['test_at_medium_threshold']}.

Beats baseline on test PR-AUC: {m['beats_baseline_on_test_pr_auc']}.

## Feature importance
Permutation importance on validation (drop in PR-AUC): {imp}.

## Error examples
See `error_examples_test` in `{c['metrics_file']}` for false negatives and false positives with their failure modes.

## Uncertainty, drift and limitations
- Scores are not calibrated (`calibrated: false`).
- Random-noise failures (RNF) are not predictable from the inputs by construction.
- Inputs outside the training ranges in `ml/artifacts/ai4i/feature_schema.json` should produce a warning.
- Single fixed-seed split; no confidence intervals were computed.
"""
