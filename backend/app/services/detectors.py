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


def miner(info: ModelInfo, readings: dict[str, ReadingValue], state: RuleState) -> Result:
    """Any rule broken for N consecutive readings is high risk; broken now but not yet sustained is medium."""
    cfg = info.rule_config
    need = cfg["consecutive_readings"]
    v = {k: _num(k, readings[k]) for k in readings}
    if v["rated_hashrate_ths"] <= 0:
        raise invalid("'rated_hashrate_ths' must be positive.", field="rated_hashrate_ths")
    ratio = v["hashrate_ths"] / v["rated_hashrate_ths"]
    checks = [  # (broken, evidence, what it means)
        (ratio < cfg["min_hashrate_ratio"],
         Evidence(type="sensor_rule", field="hashrate_ths", value=v["hashrate_ths"],
                  threshold=round(cfg["min_hashrate_ratio"] * v["rated_hashrate_ths"], 2), unit="TH/s"),
         f"hashrate is {ratio:.0%} of rated"),
        (v["chip_temp_c"] > cfg["max_chip_temp_c"],
         Evidence(type="sensor_rule", field="chip_temp_c", value=v["chip_temp_c"], threshold=cfg["max_chip_temp_c"], unit="C"),
         f"chip temperature {v['chip_temp_c']} C is above {cfg['max_chip_temp_c']} C"),
        (v["fan_speed_rpm"] < cfg["min_fan_speed_rpm"],
         Evidence(type="sensor_rule", field="fan_speed_rpm", value=v["fan_speed_rpm"], threshold=cfg["min_fan_speed_rpm"], unit="rpm"),
         f"fan speed {v['fan_speed_rpm']:.0f} rpm is below {cfg['min_fan_speed_rpm']:.0f} rpm"),
    ]
    if "hw_error_pct" in v:
        checks.append((v["hw_error_pct"] > cfg["max_hw_error_pct"],
                       Evidence(type="sensor_rule", field="hw_error_pct", value=v["hw_error_pct"],
                                threshold=cfg["max_hw_error_pct"], unit="%"),
                       f"hardware error rate {v['hw_error_pct']}% is above {cfg['max_hw_error_pct']}%"))
    broken = [c for c in checks if c[0]]
    if broken:
        state.consecutive_above += 1
    else:
        state.consecutive_above = 0
        state.cooldown_remaining = max(0, state.cooldown_remaining - 1)
    n = state.consecutive_above
    ev = [e.model_copy(update={"consecutive_readings": n}) for ok, e, _ in (broken or checks[:1])]
    if not broken:
        return Result(0.1, "low", False, f"Miner within limits (hashrate {ratio:.0%} of rated).", ev)
    what = "; ".join(t for _, _, t in broken)
    if n >= need:
        return Result(0.8, "high", state.cooldown_remaining == 0, f"Miner fault for {n} consecutive readings: {what}.", ev)
    return Result(0.5, "medium", False, f"Miner reading out of limits ({n} of {need} consecutive readings needed): {what}.", ev)


def server(info: ModelInfo, readings: dict[str, ReadingValue], state: RuleState) -> Result:
    """GPU server faults held for N consecutive readings. A stopped server or a lost GPU is high risk
    (it stalls the whole job); lost power-supply redundancy is medium (nothing lost until the second one
    fails). Heat throttling is not a server fault: it is costed on the cooling unit's incident."""
    cfg = info.rule_config
    need = cfg["consecutive_readings"]
    v = {k: _num(k, readings[k]) for k in readings}
    gpus = cfg["gpus"]
    checks = [  # (broken, high risk, evidence, what it means)
        (v["online"] < 1, True, Evidence(type="sensor_rule", field="online", value=v["online"], threshold=1, unit=None),
         "server is not responding (management controller still reports)"),
        (v["gpus_online"] < gpus, True,
         Evidence(type="sensor_rule", field="gpus_online", value=v["gpus_online"], threshold=gpus, unit="GPUs"),
         f"{gpus - int(v['gpus_online'])} of {gpus} GPUs dropped off the bus"),
        (v.get("ecc_errors", 0) > cfg["max_ecc_errors"], True,
         Evidence(type="sensor_rule", field="ecc_errors", value=v.get("ecc_errors", 0), threshold=cfg["max_ecc_errors"], unit="count"),
         f"GPU memory errors ({v.get('ecc_errors', 0):.0f}) above {cfg['max_ecc_errors']}"),
        (v["psu_ok"] < cfg["psus"], False,
         Evidence(type="sensor_rule", field="psu_ok", value=v["psu_ok"], threshold=cfg["psus"], unit="PSUs"),
         "one power supply failed; the server has no power redundancy"),
        (v.get("nic_links_up", 2) < cfg.get("nics", 2), True,
         Evidence(type="sensor_rule", field="nic_links_up", value=v.get("nic_links_up", 2), threshold=cfg.get("nics", 2), unit="links"),
         "a network link is down; the server has dropped out of the job's network"),
        (v.get("dimm_max_ecc", 0) > cfg.get("max_dimm_ecc", 100), False,
         Evidence(type="sensor_rule", field="dimm_max_ecc", value=v.get("dimm_max_ecc", 0), threshold=cfg.get("max_dimm_ecc", 100), unit="count"),
         f"a memory DIMM is logging errors ({v.get('dimm_max_ecc', 0):.0f})"),
        (v.get("nic_crc_errors", 0) > cfg.get("max_nic_crc", 100), False,
         Evidence(type="sensor_rule", field="nic_crc_errors", value=v.get("nic_crc_errors", 0), threshold=cfg.get("max_nic_crc", 100), unit="count"),
         "a network port is corrupting packets"),
        (0 <= v.get("min_fan_rpm", 9000) < cfg.get("min_fan_rpm", 3000), False,
         Evidence(type="sensor_rule", field="min_fan_rpm", value=v.get("min_fan_rpm", 9000), threshold=cfg.get("min_fan_rpm", 3000), unit="rpm"),
         "a chassis fan has slowed or stopped"),
    ]
    broken = [c for c in checks if c[0] and not (c[2].field != "online" and v["online"] < 1)]
    if broken:
        state.consecutive_above += 1
    else:
        state.consecutive_above = 0
        state.cooldown_remaining = max(0, state.cooldown_remaining - 1)
    n = state.consecutive_above
    ev = [e.model_copy(update={"consecutive_readings": n}) for _, _, e, _ in (broken or checks[:1])]
    if not broken:
        return Result(0.1, "low", False, f"Server healthy: {int(v['gpus_online'])} of {gpus} GPUs online, "
                                         f"{int(v['psu_ok'])} of {cfg['psus']} power supplies.", ev)
    what = "; ".join(t for _, _, _, t in broken)
    high = any(h for _, h, _, _ in broken)
    if n >= need:
        return Result(0.85 if high else 0.55, "high" if high else "medium", state.cooldown_remaining == 0,
                      f"GPU server fault for {n} consecutive readings: {what}.", ev)
    return Result(0.5, "medium", False, f"GPU server reading out of limits ({n} of {need} consecutive readings needed): {what}.", ev)


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
