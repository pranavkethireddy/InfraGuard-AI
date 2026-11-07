"""Detector evaluation. Each detector validates its own inputs; scores are never mixed."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..core.config import Settings
from ..core.errors import ApiError
from ..schemas.common import ReadingValue, RiskLevel
from ..schemas.models import ModelInfo
from ..schemas.predictions import Evidence
from .store import RuleState


@dataclass
class Result:
    risk_score: float
    risk_level: RiskLevel
    triggered: bool
    explanation: str
    evidence: list[Evidence]


def invalid(message: str, **details) -> ApiError:
    return ApiError(422, "INVALID_FEATURES", message, details)


def check_fields(info: ModelInfo, readings: dict[str, ReadingValue]) -> None:
    allowed = {f.name for f in info.input_fields}
    unknown = sorted(set(readings) - allowed)
    missing = sorted(f.name for f in info.input_fields if f.required and f.name not in readings)
    if unknown or missing:
        raise invalid(f"Readings do not match {info.detector_id} inputs.", unknown=unknown, missing=missing,
                      expected=sorted(allowed))


def _num(name: str, v: ReadingValue) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise invalid(f"'{name}' must be a finite number.", field=name)
    return float(v)


def cooling(info: ModelInfo, readings: dict[str, ReadingValue], state: RuleState) -> Result:
    cfg = info.rule_config
    thr, need = cfg["temperature_threshold_c"], cfg["consecutive_readings"]
    temp = _num("temperature_c", readings["temperature_c"])
    if "fan_speed_rpm" in readings:
        _num("fan_speed_rpm", readings["fan_speed_rpm"])
    if temp > thr:
        state.consecutive_above += 1
    else:
        state.consecutive_above = 0
        state.cooldown_remaining = max(0, state.cooldown_remaining - 1)
    n = state.consecutive_above
    ev = [Evidence(type="sensor_rule", field="temperature_c", value=temp, threshold=thr, unit="C", consecutive_readings=n)]
    if n >= need:
        return Result(0.8, "high", state.cooldown_remaining == 0, f"Temperature stayed above the configured {thr} C threshold for {n} consecutive readings.", ev)
    if n > 0:
        return Result(0.5, "medium", False, f"Temperature {temp} C is above the {thr} C threshold ({n} of {need} consecutive readings needed).", ev)
    return Result(0.1, "low", False, f"Temperature {temp} C is at or below the configured {thr} C threshold.", ev)


@lru_cache(maxsize=4)
def _load(path: str):
    import joblib

    return joblib.load(path)


def load_pipeline(path: str):
    if not Path(path).is_file():
        raise ApiError(503, "MODEL_UNAVAILABLE", "Model artifact is not trained or not found.", {"path": path})
    return _load(path)


def model(info: ModelInfo, readings: dict[str, ReadingValue], artifact: str) -> Result:
    import pandas as pd

    if info.risk_thresholds is None:
        raise ApiError(503, "MODEL_UNAVAILABLE", f"{info.detector_id} has no evaluated thresholds.", {})
    row = {}
    for f in info.input_fields:
        v = readings.get(f.name)
        if f.name == "type":
            if v not in ("L", "M", "H"):
                raise invalid("'type' must be one of L, M, H.", field="type")
            row[f.name] = v
        else:
            row[f.name] = float("nan") if v is None else _num(f.name, v)
    pipe = load_pipeline(artifact)
    score = float(pipe.predict_proba(pd.DataFrame([row]))[0, 1])
    t = info.risk_thresholds
    level: RiskLevel = "high" if score >= t.high else "medium" if score >= t.medium else "low"
    units = {f.name: f.unit for f in info.input_fields}
    ev = [Evidence(type="model_feature", field=k, value=readings.get(k), unit=units[k]) for k in units if k in readings]
    horizon = f" within {int(info.prediction_horizon_hours // 24)} days" if info.prediction_horizon_hours else ""
    text = {
        "high": f"Model score is above the high threshold selected on validation data (failure risk{horizon}).",
        "medium": "Model score is above the medium threshold selected on validation data.",
        "low": "Model score is below the medium threshold selected on validation data.",
    }[level]
    return Result(round(score, 6), level, level == "high", text, ev)


def artifact_for(detector_id: str, settings: Settings) -> str:
    from .model_registry import DRIVE_ID, INDUSTRIAL_ID

    return {INDUSTRIAL_ID: settings.model_artifact_path, DRIVE_ID: settings.drive_model_artifact_path}[detector_id]
