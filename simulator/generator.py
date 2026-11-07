"""Synthetic cooling scenarios; values are demo assumptions, not safety limits."""

from datetime import datetime, timedelta, timezone
import math
import random

SCENARIOS = ("normal", "cooling_anomaly")
SAMPLE_COUNT = 30


def generate(scenario: str, seed: int, asset_id: str) -> list[dict[str, float]]:
    """Return 30 independent sensor samples without I/O, timestamps, or shared state.

    Asset identity is validated but does not alter the seeded value stream. The
    backend owns asset/detector compatibility and the emission clock. Recalling
    this function with the same inputs resets the generator completely.
    """
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {SCENARIOS}")
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    if not isinstance(asset_id, str) or not asset_id.strip():
        raise ValueError("asset_id must be a non-empty string")

    rng = random.Random(seed)
    samples = []
    for index in range(SAMPLE_COUNT):
        temperature, fan = 24.5, 1150.0
        if scenario == "cooling_anomaly" and 6 <= index < 24:
            # Six baseline readings, eighteen rising, then six recovered.
            progress = (index - 5) / 18
            temperature += 12.0 * progress
            fan -= 350.0 * progress
        samples.append({
            "temperature_c": round(temperature + rng.uniform(-0.25, 0.25), 2),
            "fan_speed_rpm": round(fan + rng.uniform(-20.0, 20.0), 2),
        })
    return samples


def readings_payload(
    scenario: str,
    seed: int,
    asset_id: str,
    simulation_id: str,
    start_at: datetime,
    tick_seconds: float = 2.0,
) -> dict:
    """Build a simulated POST /readings preview from an explicit clock origin.

    The production backend should use generate() and its own emission timestamps.
    This helper is for deterministic fixtures/rehearsal, and performs no network
    operations. It never includes predictions or manufactured risk scores.
    """
    if not isinstance(simulation_id, str) or not simulation_id.strip():
        raise ValueError("simulation_id must be a non-empty string")
    if not isinstance(start_at, datetime) or start_at.utcoffset() is None:
        raise ValueError("start_at must be a timezone-aware datetime")
    if isinstance(tick_seconds, bool) or not isinstance(tick_seconds, (int, float)):
        raise ValueError("tick_seconds must be a finite positive number")
    if not math.isfinite(tick_seconds) or tick_seconds <= 0:
        raise ValueError("tick_seconds must be a finite positive number")
    start = start_at.astimezone(timezone.utc)
    readings = [
        {
            "observed_at": (start + timedelta(seconds=index * tick_seconds)).isoformat().replace("+00:00", "Z"),
            "values": values,
        }
        for index, values in enumerate(generate(scenario, seed, asset_id))
    ]
    return {
        "asset_id": asset_id,
        "data_origin": "simulated",
        "simulation_id": simulation_id,
        "readings": readings,
    }
