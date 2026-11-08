"""Detector catalogue. Each detector keeps its own input schema; scores are never mixed."""

import json
from pathlib import Path

from pydantic import ValidationError

from ..core.config import Settings
from ..schemas.models import InputField, ModelInfo, ModelMetrics, RiskThresholds

COOLING_RULE_ID = "cooling-rule-v1"
INDUSTRIAL_ID = "industrial-failure-v1"
DRIVE_ID = "drive-failure-v1"
MINER_RULE_ID = "miner-rule-v1"
SERVER_RULE_ID = "server-rule-v1"
SERVER_PART_FIELDS = (
    *[(f"cpu{i}_temp_c", "C") for i in (1, 2)], ("cpu_util_pct", "%"), ("max_cpu_temp_c", "C"),
    *[(f"dimm{i}_ecc", "count") for i in range(1, 17)], ("dimm_max_ecc", "count"),
    *[(f"fan{i}_rpm", "rpm") for i in range(1, 7)], ("min_fan_rpm", "rpm"),
    ("psu1_w", "W"), ("psu2_w", "W"), ("nic1_link", None), ("nic2_link", None), ("nic_links_up", "links"),
    ("nic_crc_errors", "count"), ("nvme1_wear_pct", "%"), ("nvme2_wear_pct", "%"), ("nvme_temp_c", "C"), ("bmc_ok", None),
)
# Facility equipment: one transparent rule detector per family. Each rule is
# (reading, op, threshold, high risk?, what it means). Thresholds are demo assumptions, not vendor limits,
# and match configs/failure_catalog.json.
FACILITY_RULES: dict[str, dict] = {
    "ups": {"name": "UPS", "target": "UPS on battery or battery runtime too short to bridge to the generator",
            "fields": {"load_pct": "%", "runtime_min": "min", "battery_charge_pct": "%", "battery_temp_c": "C",
                       "input_voltage_v": "V", "output_voltage_v": "V", "on_battery": None},
            "rules": [("on_battery", ">=", 1, True, "UPS is running on battery: utility power is lost"),
                      ("runtime_min", "<", 8, True, "battery runtime is below the 8 minutes needed to start the generator"),
                      ("battery_temp_c", ">", 30, False, "battery is running hot, which shortens its life")]},
    "generator": {"name": "Generator", "target": "standby generator would fail to start or run out of fuel",
                  "fields": {"fuel_pct": "%", "start_battery_v": "V", "coolant_temp_c": "C", "last_test_ok": None,
                             "running": None, "output_kw": "kW"},
                  "rules": [("start_battery_v", "<", 23, True, "start battery is too weak to crank the engine"),
                            ("last_test_ok", "<", 1, True, "the last start test failed"),
                            ("fuel_pct", "<", 40, False, "fuel is below the 24-hour reserve")]},
    "ats": {"name": "Transfer switch", "target": "automatic transfer switch failed to move the load to the generator",
            "fields": {"utility_voltage_v": "V", "source": None, "transfer_ok": None, "transfer_time_ms": "ms"},
            "rules": [("transfer_ok", "<", 1, True, "the switch failed to transfer"),
                      ("utility_voltage_v", "<", 432, False, "utility voltage is more than 10% below 480 V")]},
    "pdu": {"name": "Rack PDU", "target": "rack power strip near its breaker limit or badly unbalanced",
            "fields": {"phase_a_amps": "A", "phase_b_amps": "A", "phase_c_amps": "A", "breaker_rating_amps": "A",
                       "max_phase_pct": "%", "imbalance_pct": "%", "power_kw": "kW"},
            "rules": [("max_phase_pct", ">", 80, True, "a phase is above 80% of its breaker rating"),
                      ("imbalance_pct", ">", 20, False, "phase load is unbalanced by more than 20%")]},
    "chiller": {"name": "Chiller", "target": "chiller lost cooling capacity or water flow",
                "fields": {"supply_water_c": "C", "return_water_c": "C", "compressor_amps": "A", "flow_lps": "L/s"},
                "rules": [("supply_water_c", ">", 12, True, "chilled water is leaving above 12 C"),
                          ("flow_lps", "<", 20, False, "chilled water flow is low")]},
    "cdu": {"name": "Coolant distribution unit", "target": "liquid cooling loop leak or pump failure",
            "fields": {"flow_lps": "L/s", "pressure_kpa": "kPa", "coolant_supply_c": "C", "coolant_return_c": "C",
                       "leak_detected": None},
            "rules": [("leak_detected", ">=", 1, True, "the leak sensor tripped"),
                      ("flow_lps", "<", 1.5, True, "coolant flow is too low to cool the GPUs"),
                      ("coolant_supply_c", ">", 38, False, "coolant supply is hot")]},
    "env_sensor": {"name": "Hall environment", "target": "water under the floor or humidity out of range",
                   "fields": {"temperature_c": "C", "humidity_pct": "%", "dew_point_c": "C", "water_under_floor": None},
                   "rules": [("water_under_floor", ">=", 1, True, "water detected under the raised floor"),
                             ("humidity_pct", ">", 70, False, "humidity is above 70%"),
                             ("humidity_pct", "<", 20, False, "humidity is below 20% (static risk)")]},
    "network_switch": {"name": "Network switch", "target": "switch links down, failing optics or overheating",
                       "fields": {"temperature_c": "C", "cpu_pct": "%", "optic_rx_dbm": "dBm", "port_errors_per_min": "count",
                                  "links_down": "links", "packet_loss_pct": "%"},
                       "rules": [("links_down", ">", 0, True, "network links are down"),
                                 ("optic_rx_dbm", "<", -12, False, "an optic's receive power is too low"),
                                 ("packet_loss_pct", ">", 1, False, "packet loss above 1%"),
                                 ("temperature_c", ">", 60, False, "switch is overheating")]},
    "smoke_detector": {"name": "Smoke detection", "target": "smoke detected in the hall",
                       "fields": {"obscuration_pct_per_m": "%/m", "alarm_level": None},
                       "rules": [("alarm_level", ">=", 1, True, "smoke detector is in alarm"),
                                 ("obscuration_pct_per_m", ">", 0.2, False, "smoke is building up (alert level)")]},
    "fire_suppression": {"name": "Fire suppression", "target": "suppression system would not discharge correctly",
                         "fields": {"agent_pressure_pct": "%", "armed": None},
                         "rules": [("armed", "<", 1, True, "suppression panel is disarmed"),
                                   ("agent_pressure_pct", "<", 90, True, "agent cylinder pressure is below 90%")]},
    "access_control": {"name": "Door access", "target": "door forced or badge reader failing",
                       "fields": {"door_held_open_s": "s", "badge_failures_per_min": "count", "forced_open": None},
                       "rules": [("forced_open", ">=", 1, True, "door was forced open"),
                                 ("door_held_open_s", ">", 60, False, "door held open over 60 s"),
                                 ("badge_failures_per_min", ">", 5, False, "badge reads are failing")]},
}
FACILITY_RULE_IDS = {t: f"{t.replace('_', '-')}-rule-v1" for t in FACILITY_RULES}
RULE_IDS = (COOLING_RULE_ID, MINER_RULE_ID, SERVER_RULE_ID, *FACILITY_RULE_IDS.values())
GPUS_PER_SERVER = 8
DRIVE_FEATURES = [
    ("reallocated_sectors", "count"), ("reported_uncorrectable", "count"), ("command_timeout", "count"),
    ("pending_sectors", "count"), ("offline_uncorrectable", "count"), ("crc_errors", "count"),
    ("power_on_hours", "h"), ("temperature_c", "C"),
]


def load_evaluation(path: str) -> tuple[ModelMetrics, RiskThresholds] | None:
    """Read training output. Anything missing or malformed means "not evaluated", never a guess."""
    try:
        raw = json.loads(Path(path).read_text())
        return ModelMetrics.model_validate(raw["contract_metrics"]), RiskThresholds.model_validate(raw["risk_thresholds"])
    except (OSError, ValueError, KeyError, TypeError, ValidationError):
        return None


def list_models(settings: Settings) -> list[ModelInfo]:
    industrial_available = Path(settings.model_artifact_path).is_file()
    # Metrics describe the saved pipeline, so they are only reported when that pipeline is present.
    evaluation = load_evaluation(settings.industrial_metrics_path) if industrial_available else None
    metrics, thresholds = evaluation if evaluation else (None, None)
    return [
        ModelInfo(
            detector_id=COOLING_RULE_ID,
            model_name="cooling-rule",
            model_version="1.0.0",
            kind="rule",
            asset_types=["cooling_unit"],
            score_kind="heuristic",
            target="sustained supply temperature above configured threshold",
            prediction_horizon_hours=None,
            input_fields=[
                InputField(name="temperature_c", unit="C", required=True),
                InputField(name="fan_speed_rpm", unit="rpm", required=False),
            ],
            # Demo assumptions pending configs/ agreement; not facility safety specifications.
            risk_thresholds=RiskThresholds(medium=0.4, high=0.7),
            rule_config={"temperature_threshold_c": 32.0, "consecutive_readings": 3, "cooldown_readings": 3},
            status="available",
            evaluation_status="not_applicable",
            metrics=None,
            source_dataset=None,
            model_card_url=None,
            limitations=["Rule thresholds are demo assumptions, not facility safety specifications."],
        ),
        ModelInfo(
            detector_id=INDUSTRIAL_ID,
            model_name="industrial-failure",
            model_version="0.1.0",
            kind="ml",
            asset_types=["industrial_machine"],
            score_kind="model_score",
            target="AI4I 'Machine failure' at time of observation (not a forecast)",
            prediction_horizon_hours=None,
            input_fields=[
                InputField(name="type", unit=None, required=True),
                InputField(name="air_temperature_k", unit="K", required=True),
                InputField(name="process_temperature_k", unit="K", required=True),
                InputField(name="rotational_speed_rpm", unit="rpm", required=True),
                InputField(name="torque_nm", unit="Nm", required=True),
                InputField(name="tool_wear_min", unit="min", required=True),
            ],
            # Chosen on the validation split during training (max F1 for high, max F2 for medium).
            risk_thresholds=thresholds,
            rule_config=None,
            status="available" if industrial_available else "unavailable",
            # Held-out test metrics from ml/artifacts/metrics. Never filled in by hand.
            evaluation_status="evaluated" if metrics else "not_evaluated",
            metrics=metrics,
            source_dataset="UCI AI4I 2020 (id 601), CC BY 4.0",
            model_card_url=None,
            limitations=[
                "Trained on the synthetic AI4I benchmark; not validated for facility equipment.",
                "Score is not a calibrated probability.",
            ],
        ),
        _drive(settings),
        *[_facility(t) for t in FACILITY_RULES],
        ModelInfo(
            detector_id=MINER_RULE_ID,
            model_name="miner-rule",
            model_version="1.0.0",
            kind="rule",
            asset_types=["asic_miner"],
            score_kind="heuristic",
            target="sustained ASIC miner fault: hashrate drop, chip overheat, fan failure or hardware errors",
            prediction_horizon_hours=None,
            input_fields=[
                InputField(name="hashrate_ths", unit="TH/s", required=True),
                InputField(name="rated_hashrate_ths", unit="TH/s", required=True),
                InputField(name="chip_temp_c", unit="C", required=True),
                InputField(name="fan_speed_rpm", unit="rpm", required=True),
                InputField(name="power_w", unit="W", required=False),
                InputField(name="hw_error_pct", unit="%", required=False),
            ],
            risk_thresholds=RiskThresholds(medium=0.4, high=0.7),
            # Demo assumptions in the range of public miner spec sheets; not vendor limits.
            rule_config={"min_hashrate_ratio": 0.85, "max_chip_temp_c": 85.0, "min_fan_speed_rpm": 1500.0,
                         "max_hw_error_pct": 0.5, "consecutive_readings": 3, "cooldown_readings": 3},
            status="available",
            evaluation_status="not_applicable",
            metrics=None,
            source_dataset=None,
            model_card_url=None,
            limitations=["No public labelled ASIC failure dataset exists; this is a transparent rule, not a trained model.",
                         "Thresholds are demo assumptions, not vendor limits."],
        ),
        ModelInfo(
            detector_id=SERVER_RULE_ID,
            model_name="gpu-server-rule",
            model_version="1.0.0",
            kind="rule",
            asset_types=["gpu_server"],
            score_kind="heuristic",
            target="sustained GPU server fault: server not responding, GPU off the bus, GPU memory errors or lost power redundancy",
            prediction_horizon_hours=None,
            input_fields=[
                InputField(name="online", unit=None, required=True),
                InputField(name="gpus_online", unit="GPUs", required=True),
                InputField(name="psu_ok", unit="PSUs", required=True),
                InputField(name="ecc_errors", unit="count", required=False),
                InputField(name="inlet_temp_c", unit="C", required=False),
                InputField(name="gpus_throttled", unit="GPUs", required=False),
                InputField(name="max_gpu_temp_c", unit="C", required=False),
                InputField(name="min_gpu_clock_pct", unit="%", required=False),
                InputField(name="compute_pct", unit="%", required=False),
                InputField(name="power_w", unit="W", required=False),
                *[InputField(name=f"gpu{i}_{f}", unit=u, required=False)
                  for i in range(1, GPUS_PER_SERVER + 1) for f, u in (("temp_c", "C"), ("clock_pct", "%"))],
                # Server parts (all optional): CPUs, memory DIMMs, fans, PSUs, network ports, NVMe drives, BMC.
                *[InputField(name=n, unit=u, required=False) for n, u in SERVER_PART_FIELDS],
            ],
            risk_thresholds=RiskThresholds(medium=0.4, high=0.7),
            # Demo assumptions; not vendor limits.
            rule_config={"gpus": GPUS_PER_SERVER, "psus": 2, "max_ecc_errors": 10, "consecutive_readings": 3,
                         "cooldown_readings": 3},
            status="available",
            evaluation_status="not_applicable",
            metrics=None,
            source_dataset=None,
            model_card_url=None,
            limitations=["Transparent rule on simulated server telemetry, not a trained model.",
                         "Thresholds are demo assumptions, not vendor limits."],
        ),
    ]


def _drive(settings: Settings) -> ModelInfo:
    available = Path(settings.drive_model_artifact_path).is_file()
    evaluation = load_evaluation(settings.drive_metrics_path) if available else None
    metrics, thresholds = evaluation if evaluation else (None, None)
    return ModelInfo(
        detector_id=DRIVE_ID,
        model_name="drive-failure",
        model_version="0.1.0",
        kind="ml",
        asset_types=["storage_drive"],
        score_kind="model_score",
        target="Hard drive records a failure within 30 days (Backblaze Drive Stats)",
        prediction_horizon_hours=720,
        # SMART values may be missing on some drive models; the pipeline handles gaps.
        input_fields=[InputField(name=n, unit=u, required=False) for n, u in DRIVE_FEATURES],
        risk_thresholds=thresholds,
        rule_config=None,
        status="available" if available else "unavailable",
        evaluation_status="evaluated" if metrics else "not_evaluated",
        metrics=metrics,
        source_dataset="Backblaze Drive Stats Q1 2025 (real data-center drives)",
        model_card_url=None,
        limitations=[
            "One quarter of one fleet; other vendors and workloads may differ.",
            "Score is not a calibrated probability; fleet failure rate is about 0.1% per 30 days.",
            "Sudden failures with no SMART warning cannot be predicted.",
        ],
    )



def _facility(asset_type: str) -> ModelInfo:
    spec = FACILITY_RULES[asset_type]
    return ModelInfo(
        detector_id=FACILITY_RULE_IDS[asset_type], model_name=f"{asset_type.replace('_', '-')}-rule", model_version="1.0.0",
        kind="rule", asset_types=[asset_type], score_kind="heuristic", target=spec["target"], prediction_horizon_hours=None,
        input_fields=[InputField(name=n, unit=u, required=False) for n, u in spec["fields"].items()],
        risk_thresholds=RiskThresholds(medium=0.4, high=0.7),
        rule_config={"name": spec["name"], "rules": [list(r) for r in spec["rules"]], "consecutive_readings": 2,
                     "cooldown_readings": 3},
        status="available", evaluation_status="not_applicable", metrics=None, source_dataset=None, model_card_url=None,
        limitations=[f"Transparent rule on simulated {spec['name'].lower()} telemetry, not a trained model.",
                     "Thresholds are demo assumptions, not vendor limits."])
