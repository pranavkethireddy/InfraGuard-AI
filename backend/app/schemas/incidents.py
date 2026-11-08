from typing import Literal

from pydantic import AwareDatetime, Field

from .common import ContractModel, DataOrigin, ExplanationSource, IncidentStatus, InvestigationStatus, RiskLevel, ScoreKind
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
    resolved_by: Literal["operator", "reset", "technician"] | None
    prediction_count: int = Field(ge=1)
    simulation_id: str | None
    priority_index: float | None = Field(ge=0, le=1)
    # 5 = most urgent (fix first) ... 1 = least urgent. Only ever goes up, when the risk rises.
    priority_rank: int | None = Field(default=None, ge=1, le=5)


class AgentStep(ContractModel):
    """One tool call the AI agent made while investigating an incident."""

    tool: str
    summary: str


class FailureMode(ContractModel):
    """The failure playbook this incident matches (configs/failure_catalog.json), filled with its readings."""

    mode_id: str
    title: str
    cause: str
    reasoning: str
    signals: list[str]
    steps: list[str]
    repair_hours: float | None = None
    parts_cost_usd: float | None = None
    # The readings the reasoning is based on (signal -> value).
    evidence: dict[str, float] = {}


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
    agent_steps: list[AgentStep] | None = None
    # Set when the live fleet demo queues an automatic AI investigation; None for manual-only incidents.
    investigation_status: InvestigationStatus | None = None
    # Set by the investigation (additive): the problem in one sentence and its likely cause.
    problem: str | None = None
    likely_cause: str | None = None
    # Open or last work order for this incident (additive; see /ops).
    work_order_id: str | None = None
    # Matched failure playbook: named cause, reasoning and repair steps (never unknown).
    failure_mode: FailureMode | None = None


class IncidentPatchRequest(ContractModel):
    status: Literal["acknowledged", "resolved"]
    note: str | None = Field(default=None, max_length=2000)
