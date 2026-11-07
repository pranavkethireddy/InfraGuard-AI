from typing import Literal

from pydantic import AwareDatetime, Field

from .common import ContractModel, DataOrigin, ExplanationSource, IncidentStatus, RiskLevel, ScoreKind
from .impact import Impact
from .maintenance import MaintenanceSource
from .predictions import Evidence, PredictionResponse


class IncidentNote(ContractModel):
    note: str
    status: IncidentStatus
    created_at: AwareDatetime


class IncidentSummary(ContractModel):
    incident_id: str
    asset_id: str
    detector_id: str
    status: IncidentStatus
    risk_level: RiskLevel
    score_kind: ScoreKind
    data_origin: DataOrigin
    title: str
    opened_at: AwareDatetime
    last_seen_at: AwareDatetime
    acknowledged_at: AwareDatetime | None
    resolved_at: AwareDatetime | None
    resolved_by: Literal["operator", "reset"] | None
    prediction_count: int = Field(ge=1)
    simulation_id: str | None
    priority_index: float | None = Field(ge=0, le=1)


class IncidentDetail(IncidentSummary):
    latest_prediction: PredictionResponse | None
    evidence: list[Evidence]
    maintenance_sources: list[MaintenanceSource]
    explanation: str
    explanation_source: ExplanationSource
    recommended_actions: list[str]
    impact: Impact | None
    priority_weights: dict[str, float] | None
    notes: list[IncidentNote]


class IncidentPatchRequest(ContractModel):
    status: Literal["acknowledged", "resolved"]
    note: str | None = Field(default=None, max_length=2000)
