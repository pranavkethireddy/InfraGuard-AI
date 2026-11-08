"""Synthetic live readings for every machine in the demo fleet. Pure functions, no I/O or clocks.

Healthy readings wobble around a per-machine baseline so dashboards move. An injected fault
ramps one machine toward a failure signature over a few ticks, holds it, then ends:
- cooling_failure: supply temperature climbs about 13 C and the fan slows, then recovers.
- drive_degradation: SMART error counts climb and stay (counts never go down) until the
  fault ends, which models the drive being hot-swapped (counts return to the new drive's zero).
- machine_overstrain: torque and tool wear rise while speed drops (AI4I overstrain pattern), then recovers.
- fan_failure (ASIC miner): fans slow and chips heat up; the miner throttles its hashrate, then recovers.
- hashboard_failure (ASIC miner): one of three hashboards drops out (hashrate and power fall by a third,
  hardware errors climb) and stays out until the fault ends, which models the board being swapped.
Values are demo assumptions, not facility specifications. No risk scores or costs are produced here.
"""

from __future__ import annotations

import hashlib
import math
import random

FAULT_KINDS = {
    "cooling_unit": "cooling_failure",
    "storage_drive": "drive_degradation",
    "industrial_machine": "machine_overstrain",
    "asic_miner": "hashboard_failure",
}
# Every fault an asset type can get; FAULT_KINDS holds the default one.
FAULT_CHOICES = {t: (k,) for t, k in FAULT_KINDS.items()} | {"asic_miner": ("hashboard_failure", "fan_failure")}
# (ramp, hold, recover) in ticks.
FAULT_TICKS = {
    "cooling_failure": (6, 30, 6),
    "drive_degradation": (4, 36, 0),
    "machine_overstrain": (6, 30, 6),
    "fan_failure": (5, 30, 5),
    "hashboard_failure": (3, 37, 0),
}
# Faults that keep getting worse while nobody fixes them: degrees added per unit of progress above 1.
# Progress may go up to MAX_ESCALATION for these (the backend drives it from configs/operations.json).
ESCALATING = {"cooling_failure": 13.0, "fan_failure": 28.0}
MAX_ESCALATION = 2.0
# ASIC miner spec-sheet-class demo values (about 200 TH/s at 3.5 kW); must match configs/mining_layout.json.
MINER_RATED_THS = 200.0
MINER_RATED_W = 3500.0


def rng_for(seed: int, asset_id: str) -> random.Random:
    """Independent, repeatable random stream per (seed, machine)."""
    digest = hashlib.sha256(f"{seed}:{asset_id}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def profile(asset_type: str, asset_id: str, seed: int) -> dict:
    """Stable per-machine baseline, so machines of one type do not move in lockstep."""
    r = rng_for(seed, "profile:" + asset_id)
    base = {"phase": r.uniform(0, 2 * math.pi)}
    if asset_type == "cooling_unit":
        return base | {"setpoint_c": r.uniform(22.5, 24.5), "fan_rpm": r.uniform(1100, 1200)}
    if asset_type == "storage_drive":
        return base | {"temp_c": r.uniform(29, 35), "power_on_hours": r.randint(8000, 42000),
                       "reallocated_sectors": r.choice([0, 0, 0, 0, 2, 8])}
    if asset_type == "industrial_machine":
        return base | {"type": r.choice(["L", "M", "H"]), "air_k": r.uniform(299, 301), "rpm": r.uniform(1450, 1550),
                       "torque_nm": r.uniform(36, 44), "wear0": r.uniform(10, 60)}
    if asset_type == "asic_miner":
        return base | {"eff": r.uniform(0.97, 1.02), "chip_c": r.uniform(64, 74), "fan_rpm": r.uniform(4200, 5400)}
    raise ValueError(f"unknown asset_type {asset_type!r}")


def fault_kind(asset_type: str, rng: random.Random) -> str:
    return rng.choice(FAULT_CHOICES[asset_type])


def fault_phase(kind: str, ticks_since_injected: int) -> tuple[str, float]:
    """(phase, progress 0..1) of a fault ticks_since_injected ticks after injection."""
    ramp, hold, recover = FAULT_TICKS[kind]
    t = ticks_since_injected
    if t < ramp:
        return "ramping", (t + 1) / ramp
    if t < ramp + hold:
        return "holding", 1.0
    if t < ramp + hold + recover:
        return "recovering", 1.0 - (t - ramp - hold + 1) / recover
    return "ended", 0.0


def sample(asset_type: str, prof: dict, tick: int, rng: random.Random, progress: float = 0.0,
           kind: str | None = None) -> dict:
    """One reading for one machine. progress is the fault severity (0 healthy, 1 full failure signature);
    kind picks the signature for types with several faults (default FAULT_KINDS[asset_type])."""
    cap = MAX_ESCALATION if (kind or FAULT_KINDS.get(asset_type)) in ESCALATING else 1.0
    p = min(max(progress, 0.0), cap)
    wave = math.sin(tick / 6 + prof["phase"])
    if asset_type == "cooling_unit":
        # Cooling escalates past progress 1 (kept by cap above); everything else is clamped to 1 below.
        return {"temperature_c": round(prof["setpoint_c"] + 0.8 * wave + rng.uniform(-0.3, 0.3) + 13.0 * p, 2),
                "fan_speed_rpm": round(max(0.0, prof["fan_rpm"] + 25 * wave + rng.uniform(-20, 20) - 380 * p), 1)}
    p = min(p, 1.0) if asset_type != "asic_miner" else p
    if asset_type == "storage_drive":
        return {"reallocated_sectors": prof["reallocated_sectors"] + round(5000 * p),
                "reported_uncorrectable": round(300 * p), "command_timeout": 0,
                "pending_sectors": round(800 * p), "offline_uncorrectable": round(800 * p), "crc_errors": 0,
                "power_on_hours": prof["power_on_hours"] + tick // 60,
                "temperature_c": round(prof["temp_c"] + 1.2 * wave + rng.uniform(-0.4, 0.4) + 4 * p, 1)}
    if asset_type == "asic_miner":
        return miner_sample(prof, wave, rng, p, kind or FAULT_KINDS["asic_miner"])
    if asset_type == "industrial_machine":
        air = prof["air_k"] + 0.4 * wave + rng.uniform(-0.1, 0.1)
        return {"type": prof["type"], "air_temperature_k": round(air, 2),
                "process_temperature_k": round(air + 10 + rng.uniform(-0.2, 0.2), 2),
                "rotational_speed_rpm": round(prof["rpm"] + 30 * wave + rng.uniform(-25, 25) - 250 * p),
                "torque_nm": round(prof["torque_nm"] + 2 * wave + rng.uniform(-1.5, 1.5) + 28 * p, 1),
                # Fault pulls wear toward 230 min; with high torque this crosses AI4I's overstrain limit.
                "tool_wear_min": round((1 - p) * (prof["wear0"] + (tick // 10) % 90) + p * 230)}
    raise ValueError(f"unknown asset_type {asset_type!r}")


def miner_sample(prof: dict, wave: float, rng: random.Random, p: float, kind: str) -> dict:
    """ASIC miner reading. kind picks the fault signature; p is its severity."""
    fan = p if kind == "fan_failure" else 0.0
    board = min(p, 1.0) if kind == "hashboard_failure" else 0.0
    ths = MINER_RATED_THS * prof["eff"] * (1 - board / 3) * (1 - 0.25 * min(fan, 1.0))
    return {"hashrate_ths": round(ths + 2.5 * wave + rng.uniform(-2, 2), 1), "rated_hashrate_ths": MINER_RATED_THS,
            "chip_temp_c": round(prof["chip_c"] + 1.5 * wave + rng.uniform(-0.8, 0.8) + 28 * fan, 1),
            "fan_speed_rpm": round((prof["fan_rpm"] + 120 * wave + rng.uniform(-60, 60)) * max(0.0, 1 - 0.9 * min(fan, 1.0))),
            "power_w": round(MINER_RATED_W * (1 - board / 3) * (1 - 0.2 * min(fan, 1.0)) + rng.uniform(-30, 30)),
            "hw_error_pct": round(max(0.0, 0.02 + rng.uniform(-0.015, 0.015) + 2.0 * board + 0.3 * min(fan, 1.0)), 3)}
