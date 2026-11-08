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
- GPU server (8 GPUs): GPU temperatures follow the inlet air from the rack's cooling unit; a GPU above
  THROTTLE_C slows its clock to protect itself. gpu_fault: one GPU heats up and logs memory (ECC) errors,
  then drops off the bus. psu_failure: one of two power supplies dies (no lost compute, no redundancy).
  server_crash: the server stops (the management controller still reports).
  Server parts (2 CPUs, 16 memory DIMMs, 6 fans, 2 PSUs, 2 NICs, 2 NVMe drives) report too. memory_fault: one
  DIMM's ECC errors climb. nic_failure: one network port's CRC errors climb, then its link drops.
  server_fan_failure: one chassis fan slows and stops, so the GPUs run a few degrees hotter.
- Facility equipment (FACILITY below: UPS, generator, transfer switch, rack PDU, chiller, coolant distribution
  unit, hall environment sensor, network switch, smoke detector, fire suppression, door access): each reading
  wobbles around a healthy baseline; a fault moves its listed readings toward the fault's target values.
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
    "gpu_server": "gpu_fault",
}
# Every fault an asset type can get; FAULT_KINDS holds the default one.
FAULT_CHOICES = {t: (k,) for t, k in FAULT_KINDS.items()} | {"asic_miner": ("hashboard_failure", "fan_failure"),
                                                          "gpu_server": ("gpu_fault", "psu_failure", "server_crash")}
# Faults that only happen when asked for by kind (kept out of FAULT_CHOICES so seeded random draws stay the same).
FAULT_EXPLICIT = {"gpu_server": ("memory_fault", "nic_failure", "server_fan_failure")}
# Facility equipment: healthy baseline per reading as (value, wobble), and per fault the readings it moves and
# where to. Flags (0/1) and counts are rounded. Readings and thresholds match configs/failure_catalog.json.
FACILITY: dict[str, dict] = {
    "ups": {"base": {"load_pct": (55, 3), "runtime_min": (14, 0.4), "battery_charge_pct": (100, 0), "battery_temp_c": (25, 0.6),
                     "input_voltage_v": (480, 2), "output_voltage_v": (480, 0.5), "on_battery": (0, 0)},
            "faults": {"ups_battery_fade": {"runtime_min": 5.0, "battery_temp_c": 34.0, "battery_charge_pct": 93.0},
                       "ups_on_battery": {"on_battery": 1, "input_voltage_v": 0.0, "battery_charge_pct": 55.0, "runtime_min": 9.0}}},
    "generator": {"base": {"fuel_pct": (92, 0.3), "start_battery_v": (26, 0.15), "coolant_temp_c": (45, 1), "last_test_ok": (1, 0),
                           "running": (0, 0), "output_kw": (0, 0)},
                  "faults": {"gen_start_battery": {"start_battery_v": 21.5, "last_test_ok": 0},
                             "gen_low_fuel": {"fuel_pct": 24.0}}},
    "ats": {"base": {"utility_voltage_v": (480, 2), "source": (0, 0), "transfer_ok": (1, 0), "transfer_time_ms": (0, 0)},
            "faults": {"ats_transfer_fail": {"utility_voltage_v": 0.0, "transfer_ok": 0},
                       "ats_utility_sag": {"utility_voltage_v": 405.0}}},
    "pdu": {"base": {"phase_a_amps": (18, 0.6), "phase_b_amps": (17.5, 0.6), "phase_c_amps": (18.2, 0.6), "breaker_rating_amps": (32, 0)},
            "faults": {"pdu_overload": {"phase_a_amps": 29.5, "phase_b_amps": 28.0, "phase_c_amps": 27.5},
                       "pdu_imbalance": {"phase_a_amps": 24.5, "phase_b_amps": 12.0, "phase_c_amps": 11.0}}},
    "chiller": {"base": {"supply_water_c": (7, 0.2), "return_water_c": (12.5, 0.3), "compressor_amps": (180, 4), "flow_lps": (32, 0.5)},
                "faults": {"chiller_trip": {"supply_water_c": 15.5, "return_water_c": 17.0, "compressor_amps": 15.0},
                           "chiller_low_flow": {"flow_lps": 12.0, "supply_water_c": 9.5}}},
    "cdu": {"base": {"flow_lps": (2.5, 0.05), "pressure_kpa": (250, 3), "coolant_supply_c": (32, 0.3), "coolant_return_c": (42, 0.4),
                     "leak_detected": (0, 0)},
            "faults": {"cdu_leak": {"leak_detected": 1, "pressure_kpa": 110.0, "flow_lps": 1.2},
                       "cdu_pump_failure": {"flow_lps": 0.6, "coolant_supply_c": 41.0, "coolant_return_c": 55.0}}},
    "env_sensor": {"base": {"temperature_c": (23, 0.4), "humidity_pct": (45, 1.5), "dew_point_c": (10.6, 0.4), "water_under_floor": (0, 0)},
                   "faults": {"env_water_leak": {"water_under_floor": 1, "humidity_pct": 62.0},
                              "env_high_humidity": {"humidity_pct": 78.0, "dew_point_c": 19.0}}},
    "network_switch": {"base": {"temperature_c": (42, 1), "cpu_pct": (25, 3), "optic_rx_dbm": (-3.0, 0.2), "port_errors_per_min": (0, 0),
                                "links_down": (0, 0), "packet_loss_pct": (0.0, 0)},
                       "faults": {"switch_optic_degraded": {"optic_rx_dbm": -15.0, "port_errors_per_min": 400, "packet_loss_pct": 1.5},
                                  "switch_link_down": {"links_down": 4, "packet_loss_pct": 6.0}}},
    "smoke_detector": {"base": {"obscuration_pct_per_m": (0.01, 0.003), "alarm_level": (0, 0)},
                       "faults": {"smoke_alarm": {"obscuration_pct_per_m": 1.4, "alarm_level": 2}}},
    "fire_suppression": {"base": {"agent_pressure_pct": (100, 0.2), "armed": (1, 0)},
                         "faults": {"suppression_pressure_loss": {"agent_pressure_pct": 78.0},
                                    "suppression_disarmed": {"armed": 0}}},
    "access_control": {"base": {"door_held_open_s": (0, 0), "badge_failures_per_min": (0, 0), "forced_open": (0, 0)},
                       "faults": {"door_forced": {"forced_open": 1, "door_held_open_s": 120.0},
                                  "badge_reader_failure": {"badge_failures_per_min": 14}}},
}
FLAGS = {"on_battery", "last_test_ok", "running", "source", "transfer_ok", "leak_detected", "water_under_floor", "links_down",
         "port_errors_per_min", "alarm_level", "armed", "forced_open", "badge_failures_per_min", "breaker_rating_amps"}
FAULT_KINDS |= {t: next(iter(f["faults"])) for t, f in FACILITY.items()}
FAULT_CHOICES |= {t: tuple(f["faults"]) for t, f in FACILITY.items()}
# (ramp, hold, recover) in ticks.
FAULT_TICKS = {
    "cooling_failure": (6, 30, 6),
    "drive_degradation": (4, 36, 0),
    "machine_overstrain": (6, 30, 6),
    "fan_failure": (5, 30, 5),
    "hashboard_failure": (3, 37, 0),
    "gpu_fault": (4, 36, 0),
    "psu_failure": (2, 38, 0),
    "server_crash": (1, 39, 0),
    "memory_fault": (4, 36, 0),
    "nic_failure": (3, 37, 0),
    "server_fan_failure": (3, 37, 0),
} | {k: (3, 33, 4) for f in FACILITY.values() for k in f["faults"]}
# Faults that keep getting worse while nobody fixes them: degrees added per unit of progress above 1.
# Progress may go up to MAX_ESCALATION for these (the backend drives it from configs/operations.json).
ESCALATING = {"cooling_failure": 13.0, "fan_failure": 28.0}
MAX_ESCALATION = 2.0
# ASIC miner spec-sheet-class demo values (about 200 TH/s at 3.5 kW); must match configs/mining_layout.json.
MINER_RATED_THS = 200.0
MINER_RATED_W = 3500.0
# GPU server demo values (8 GPUs, data-center accelerator class); must match configs/datacenter_layout.json.
GPUS_PER_SERVER = 8
THROTTLE_C = 83.0  # GPU temperature where the clock starts to drop
GPU_HEAT_C = 50.0  # GPU temperature above inlet air at full load
CPUS, DIMMS, FANS, NICS, NVMES = 2, 16, 6, 2, 2
FAN_RPM = 9000.0


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
    if asset_type in FACILITY:
        return base | {k: v + r.uniform(-1, 1) * w * 0.3 for k, (v, w) in FACILITY[asset_type]["base"].items()}
    if asset_type == "gpu_server":
        prof = base | {"load": r.uniform(0.86, 0.96), "offsets": [r.uniform(-3, 5) for _ in range(GPUS_PER_SERVER)],
                       "faulty_gpu": r.randrange(GPUS_PER_SERVER)}
        q = rng_for(seed, "parts:" + asset_id)  # own stream: adding parts does not move the GPU baseline
        return prof | {"faulty_dimm": q.randrange(DIMMS), "faulty_fan": q.randrange(FANS), "faulty_nic": q.randrange(NICS),
                       "nvme_wear": [round(q.uniform(3, 40), 1) for _ in range(NVMES)],
                       "fan_rpm": [q.uniform(8600, 9400) for _ in range(FANS)]}
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
           kind: str | None = None, inlet_c: float | None = None) -> dict:
    """One reading for one machine. progress is the fault severity (0 healthy, 1 full failure signature);
    kind picks the signature for types with several faults (default FAULT_KINDS[asset_type]).
    inlet_c (GPU servers only) is the supply air temperature of the rack's cooling unit."""
    cap = MAX_ESCALATION if (kind or FAULT_KINDS.get(asset_type)) in ESCALATING else 1.0
    p = min(max(progress, 0.0), cap)
    wave = math.sin(tick / 6 + prof["phase"])
    if asset_type == "cooling_unit":
        # Cooling escalates past progress 1 (kept by cap above); everything else is clamped to 1 below.
        return {"temperature_c": round(prof["setpoint_c"] + 0.8 * wave + rng.uniform(-0.3, 0.3) + 13.0 * p, 2),
                "fan_speed_rpm": round(max(0.0, prof["fan_rpm"] + 25 * wave + rng.uniform(-20, 20) - 380 * p), 1)}
    p = min(p, 1.0) if asset_type != "asic_miner" else p
    if asset_type in FACILITY:
        return facility_sample(asset_type, prof, wave, rng, p, kind or FAULT_KINDS[asset_type])
    if asset_type == "storage_drive":
        return {"reallocated_sectors": prof["reallocated_sectors"] + round(5000 * p),
                "reported_uncorrectable": round(300 * p), "command_timeout": 0,
                "pending_sectors": round(800 * p), "offline_uncorrectable": round(800 * p), "crc_errors": 0,
                "power_on_hours": prof["power_on_hours"] + tick // 60,
                "temperature_c": round(prof["temp_c"] + 1.2 * wave + rng.uniform(-0.4, 0.4) + 4 * p, 1)}
    if asset_type == "asic_miner":
        return miner_sample(prof, wave, rng, p, kind or FAULT_KINDS["asic_miner"])
    if asset_type == "gpu_server":
        return server_sample(prof, wave, rng, p, kind or FAULT_KINDS["gpu_server"], 23.5 if inlet_c is None else inlet_c)
    if asset_type == "industrial_machine":
        air = prof["air_k"] + 0.4 * wave + rng.uniform(-0.1, 0.1)
        return {"type": prof["type"], "air_temperature_k": round(air, 2),
                "process_temperature_k": round(air + 10 + rng.uniform(-0.2, 0.2), 2),
                "rotational_speed_rpm": round(prof["rpm"] + 30 * wave + rng.uniform(-25, 25) - 250 * p),
                "torque_nm": round(prof["torque_nm"] + 2 * wave + rng.uniform(-1.5, 1.5) + 28 * p, 1),
                # Fault pulls wear toward 230 min; with high torque this crosses AI4I's overstrain limit.
                "tool_wear_min": round((1 - p) * (prof["wear0"] + (tick // 10) % 90) + p * 230)}
    raise ValueError(f"unknown asset_type {asset_type!r}")


def facility_sample(asset_type: str, prof: dict, wave: float, rng: random.Random, p: float, kind: str) -> dict:
    """Facility equipment reading: healthy wobble, pulled toward the fault's targets by p."""
    spec = FACILITY[asset_type]
    target = spec["faults"].get(kind, {}) if p > 0 else {}
    out: dict = {}
    for k, (_, w) in spec["base"].items():
        v = prof[k] if k in FLAGS else prof[k] + w * wave + rng.uniform(-0.3, 0.3) * w
        if k in target:
            v = (1 - p) * v + p * target[k]
        out[k] = round(v) if k in FLAGS else round(v, 2)
    if asset_type == "pdu":
        ph = [out["phase_a_amps"], out["phase_b_amps"], out["phase_c_amps"]]
        mean = sum(ph) / 3
        out["max_phase_pct"] = round(100 * max(ph) / out["breaker_rating_amps"], 1)
        out["imbalance_pct"] = round(100 * (max(ph) - min(ph)) / mean, 1) if mean else 0.0
        out["power_kw"] = round(sum(ph) * 0.23, 2)  # 230 V per phase
    if asset_type == "ats" and out["transfer_ok"] == 1 and out["utility_voltage_v"] < 300:
        out["source"] = 1  # on generator
    return out


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


def gpu_throttle(raw_c: float) -> tuple[float, float]:
    """(reported temperature, clock fraction) for a GPU whose unthrottled temperature would be raw_c.
    Above THROTTLE_C the clock drops 3.5% per degree (to at most half speed), which holds the
    temperature down to a fraction of the excess."""
    if raw_c <= THROTTLE_C:
        return raw_c, 1.0
    return THROTTLE_C + 0.35 * (raw_c - THROTTLE_C), max(0.5, 1 - 0.035 * (raw_c - THROTTLE_C))


def server_sample(prof: dict, wave: float, rng: random.Random, p: float, kind: str, inlet_c: float) -> dict:
    """GPU server reading: per-GPU temperature and clock, plus server totals. Values are demo assumptions."""
    inlet = inlet_c + rng.uniform(-0.3, 0.3)
    crashed = kind == "server_crash" and p > 0
    bad = prof["faulty_gpu"] if kind == "gpu_fault" else None
    dead = bad is not None and p >= 1.0
    temps, clocks = [], []
    for i, off in enumerate(prof["offsets"]):
        if crashed or (dead and i == bad):
            temps.append(round(inlet + 4 + rng.uniform(-0.5, 0.5), 1))
            clocks.append(0.0)
            continue
        raw = inlet + GPU_HEAT_C * prof["load"] + off + 1.0 * wave + rng.uniform(-0.6, 0.6)
        if i == bad:
            raw += 18 * p
        t, c = gpu_throttle(raw)
        temps.append(round(t, 1))
        clocks.append(round(c, 3))
    online = [c for c in clocks if c > 0]
    values = {
        "inlet_temp_c": round(inlet, 2), "online": 0 if crashed else 1, "gpus_online": len(online),
        "gpus_throttled": sum(1 for c in online if c < 0.99),
        "max_gpu_temp_c": max(temps), "min_gpu_clock_pct": round(100 * min(online), 1) if online else 0.0,
        "compute_pct": round(100 * sum(clocks) / GPUS_PER_SERVER, 1),
        "ecc_errors": round(60 * min(p, 1.0)) if bad is not None else 0,
        "psu_ok": 1 if kind == "psu_failure" and p >= 0.5 else 2,
        "power_w": round(250 if crashed else 1200 + sum(700 * prof["load"] * c for c in clocks) + rng.uniform(-40, 40)),
    }
    values |= {f"gpu{i + 1}_temp_c": t for i, t in enumerate(temps)}
    values |= {f"gpu{i + 1}_clock_pct": round(100 * c, 1) for i, c in enumerate(clocks)}
    return values | _server_parts(prof, wave, rng, p, kind, inlet, crashed, values["power_w"])


def _server_parts(prof: dict, wave: float, rng: random.Random, p: float, kind: str, inlet: float, crashed: bool,
                  power_w: float) -> dict:
    """CPUs, memory, fans, power supplies, network ports and NVMe drives inside a GPU server."""
    pp = min(p, 1.0)
    load = 0.0 if crashed else prof["load"]
    out: dict = {}
    fans = []
    for i in range(FANS):
        rpm = prof.get("fan_rpm", [FAN_RPM] * FANS)[i] * (0.35 + 0.65 * load) + 120 * wave + rng.uniform(-80, 80)
        if kind == "server_fan_failure" and i == prof.get("faulty_fan", 0):
            rpm *= max(0.0, 1 - pp)
        fans.append(max(0.0, round(rpm)))
    out |= {f"fan{i + 1}_rpm": f for i, f in enumerate(fans)}
    hot = 6.0 * pp if kind == "server_fan_failure" else 0.0
    cpus = [round(inlet + 8 + 40 * load + hot + 1.5 * wave + rng.uniform(-1, 1), 1) for _ in range(CPUS)]
    out |= {f"cpu{i + 1}_temp_c": t for i, t in enumerate(cpus)}
    out["cpu_util_pct"] = round(min(100.0, 100 * load * 0.7 + 5 * wave + rng.uniform(-3, 3)), 1) if not crashed else 0.0
    dimms = [0] * DIMMS
    if kind == "memory_fault":
        dimms[prof.get("faulty_dimm", 0)] = round(400 * pp)
    out |= {f"dimm{i + 1}_ecc": e for i, e in enumerate(dimms)}
    bad_nic = prof.get("faulty_nic", 0) if kind == "nic_failure" else None
    links = [0 if (crashed or (i == bad_nic and pp >= 0.6)) else 1 for i in range(NICS)]
    out |= {f"nic{i + 1}_link": v for i, v in enumerate(links)}
    out["nic_crc_errors"] = round(800 * pp) if bad_nic is not None else 0
    psu_dead = kind == "psu_failure" and p >= 0.5
    out |= {"psu1_w": round(power_w if psu_dead else power_w / 2), "psu2_w": 0 if psu_dead else round(power_w / 2)}
    wear = prof.get("nvme_wear", [10.0] * NVMES)
    out |= {f"nvme{i + 1}_wear_pct": w for i, w in enumerate(wear)}
    out["nvme_temp_c"] = round(inlet + 12 + 3 * load + rng.uniform(-0.5, 0.5), 1)
    out |= {"bmc_ok": 1, "max_cpu_temp_c": max(cpus), "min_fan_rpm": min(fans), "dimm_max_ecc": max(dimms),
            "nic_links_up": sum(links)}
    return out
