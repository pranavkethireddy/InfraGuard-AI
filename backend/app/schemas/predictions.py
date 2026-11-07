from typing import Literal

from pydantic import AwareDatetime, Field

from .common import ContractModel, DataOrigin, ExplanationSource, ReadingValue, RiskLevel, ScoreKind
from .maintenance import MaintenanceSource


class Evidence(ContractModel):
    type: Literal["sensor_rule", "model_feature"]
    field: str
    value: ReadingValue | None
    threshold: float | None = None
    unit: str | None = None
    consecutive_readings: int | None = None


class PredictionRequest(ContractModel):
    asset_id: str
    observed_at: AwareDatetime
    data_origin: DataOrigin
    detector_id: str
    readings: dict[str, ReadingValue] = Field(min_length=1)


class PredictionResponse(ContractModel):
    prediction_id: str
    asset_id: str
    detector_id: str
    observed_at: AwareDatetime
    generated_at: AwareDatetime
    data_origin: DataOrigin
    model_name: str
    model_version: str
    target: str
    risk_score: float = Field(ge=0, le=1)
    score_kind: ScoreKind
    risk_level: RiskLevel
    prediction_horizon_hours: float | None = Field(default=None, gt=0)
    explanation: str
    explanation_source: ExplanationSource
    evidence: list[Evidence]
    maintenance_sources: list[MaintenanceSource]
    limitations: list[str]
    incident_id: str | None
