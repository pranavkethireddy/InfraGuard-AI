"""Detector catalogue. Each detector keeps its own input schema; scores are never mixed."""

from pathlib import Path

from ..core.config import Settings
from ..schemas.models import InputField, ModelInfo, RiskThresholds

COOLING_RULE_ID = "cooling-rule-v1"
INDUSTRIAL_ID = "industrial-failure-v1"


def list_models(settings: Settings) -> list[ModelInfo]:
    industrial_available = Path(settings.model_artifact_path).is_file()
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
            # Thresholds are chosen on validation data during training; unknown until then.
            risk_thresholds=None,
            rule_config=None,
            status="available" if industrial_available else "unavailable",
            # Metrics come from ml/artifacts/metrics once training exists. Never filled in by hand.
            evaluation_status="not_evaluated",
            metrics=None,
            source_dataset="UCI AI4I 2020 (id 601), CC BY 4.0",
            model_card_url=None,
            limitations=[
                "Trained on the synthetic AI4I benchmark; not validated for facility equipment.",
                "Score is not a calibrated probability.",
            ],
        ),
    ]
