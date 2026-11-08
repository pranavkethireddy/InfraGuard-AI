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
RULE_IDS = (COOLING_RULE_ID, MINER_RULE_ID, SERVER_RULE_ID)
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

