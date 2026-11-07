from typing import Any, Literal

from pydantic import Field

from .common import ContractModel, ScoreKind


class InputField(ContractModel):
    name: str
    unit: str | None
    required: bool


class RiskThresholds(ContractModel):
    medium: float = Field(ge=0, le=1)
    high: float = Field(ge=0, le=1)


class ModelInfo(ContractModel):
    detector_id: str
    model_name: str
    model_version: str
    kind: Literal["rule", "ml"]
    asset_types: list[str]
    score_kind: ScoreKind
    target: str
    prediction_horizon_hours: float | None
    input_fields: list[InputField]
    risk_thresholds: RiskThresholds | None
    rule_config: dict[str, Any] | None
    status: Literal["available", "unavailable"]
    evaluation_status: Literal["evaluated", "not_evaluated", "not_applicable"]
    metrics: dict[str, Any] | None
    source_dataset: str | None
    model_card_url: str | None
    limitations: list[str]
