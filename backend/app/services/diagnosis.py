"""Likely cause from the symptom pattern in a machine's latest reading.

Rules of thumb a technician would use (fan slowing while supply air heats up = slipping fan belt, and so on).
The agent gets this as evidence, and it is the likely cause whenever the agent cannot name one.
Returns None when the readings do not point to a cause."""

from __future__ import annotations

# Normal running values for the equipment (the simulator's healthy range).
CRAC_FAN_RPM = 1150
CRAC_SUPPLY_C = 24.0


def _cooling(v: dict) -> str | None:
    t, rpm = v.get("temperature_c"), v.get("fan_speed_rpm")
    if t is None or rpm is None or t < CRAC_SUPPLY_C + 3:
        return None
    if rpm < CRAC_FAN_RPM * 0.88:
        return (f"Worn or slipping fan belt: the fan slowed to {rpm:,.0f} rpm (normal about {CRAC_FAN_RPM:,}) "
                f"while supply air rose to {t:.1f} C, so less air is moving across the coil.")
    return (f"Clogged air filter or low refrigerant: supply air is {t:.1f} C with the fan at normal speed "
            f"({rpm:,.0f} rpm). Check the filter first (cheapest), then refrigerant pressure.")


def _drive(v: dict) -> str | None:
    bad = v.get("reallocated_sectors", 0) + v.get("pending_sectors", 0)
    if bad < 50 and v.get("reported_uncorrectable", 0) < 5:
        return None
    return (f"The disk surface is failing: {v.get('reallocated_sectors', 0):,} sectors remapped, "
            f"{v.get('pending_sectors', 0):,} pending and {v.get('reported_uncorrectable', 0):,} unreadable. "
            "Copy the data off and replace the drive.")


def _miner(v: dict) -> str | None:
    rpm, chip = v.get("fan_speed_rpm"), v.get("chip_temp_c")
    if rpm is not None and chip is not None and rpm < 3500 and chip > 85:
        return f"Cooling fan failure: the fan is at {rpm:,.0f} rpm and the chips reached {chip:.1f} C."
    rated, ths, err = v.get("rated_hashrate_ths"), v.get("hashrate_ths"), v.get("hw_error_pct", 0)
    if rated and ths is not None and (ths < 0.85 * rated or err > 0.5):
        return (f"A hashboard is failing: hashrate is {ths:.0f} of {rated:.0f} TH/s with "
                f"{err:.2f}% hardware errors, while the fan and chip temperature are normal.")
    return None


def _server(v: dict) -> str | None:
    if v.get("online") == 0:
        return "The server crashed (hung or lost power): it stopped answering and all 8 GPUs went offline."
    if v.get("gpus_online", 8) < 8:
        return (f"A GPU dropped off the bus ({v.get('gpus_online')} of 8 online), after its ECC memory errors climbed "
                f"to {v.get('ecc_errors', 0)}: that GPU is failing and needs replacing.")
    if v.get("ecc_errors", 0) > 10:
        return f"A GPU's memory is failing: {v.get('ecc_errors')} ECC errors and that GPU is running hot."
    if v.get("psu_ok", 2) < 2:
        return "One of the two power supplies failed; the server runs on the other with no redundancy left."
    if v.get("gpus_throttled", 0) > 0:
        return (f"Hot inlet air from the rack's cooling unit ({v.get('inlet_temp_c', 0):.1f} C): "
                f"{v.get('gpus_throttled')} GPUs are throttling to protect themselves. The fix is the cooling unit.")
    return None


def _machine(v: dict) -> str | None:
    wear, torque = v.get("tool_wear_min"), v.get("torque_nm")
    if wear is not None and torque is not None and wear > 150 and torque > 55:
        return (f"Overstrain: torque is {torque:.1f} Nm on a tool with {wear:.0f} minutes of wear, "
                "so the load is more than the worn tool can take. Replace the tool and reduce the load.")
    if wear is not None and wear > 200:
        return f"Tool wear: the tool has run {wear:.0f} minutes and is near the end of its life."
    if torque is not None and torque > 60:
        return f"Overstrain: torque is {torque:.1f} Nm, above the safe working load."
    return None


RULES = {"cooling_unit": _cooling, "storage_drive": _drive, "asic_miner": _miner,
         "gpu_server": _server, "industrial_machine": _machine}


def likely_cause(asset_type: str, values: dict | None) -> str | None:
    rule = RULES.get(asset_type)
    return rule(values) if rule and values else None


def is_unknown(text: str | None) -> bool:
    return not text or "unknown" in text.lower() or "not clear" in text.lower() or "cannot be determined" in text.lower()
