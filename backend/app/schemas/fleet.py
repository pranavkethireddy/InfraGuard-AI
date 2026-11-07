"""Fleet view: floor map, rack status, machine status and the live demo controls."""

from typing import Literal

from pydantic import AwareDatetime, Field

from .common import ContractModel, Criticality, InvestigationStatus, ReadingValue, RiskLevel
from .incidents import IncidentSummary

# critical: unresolved high-risk incident or latest risk high; warning: medium risk, any other unresolved
# incident, or (racks) a cooling unit serving the rack is not healthy; healthy: latest risk low; no_data: no readings.
HealthStatus = Literal["healthy", "warning", "critical", "no_data"]
LiveState = Literal["running", "stopped"]
FaultKind = Literal["cooling_failure", "drive_degradation", "machine_overstrain"]
FaultPhase = Literal["ramping", "holding", "recovering", "ended"]


class Placement(ContractModel):
    hall_id: str
    row: str | None
    rack_id: str | None
    slot: int | None
    x: float
    y: float


class HistoryPoint(ContractModel):
    observed_at: AwareDatetime
    values: dict[str, ReadingValue]


class IncidentBrief(ContractModel):
    incident_id: str
    title: str
    status: Literal["open", "acknowledged"]
    risk_level: RiskLevel
    opened_at: AwareDatetime
    estimated_total_impact: float | None
    cost_per_day: float | None
    investigation_status: InvestigationStatus | None


class FaultInfo(ContractModel):
    asset_id: str
    kind: FaultKind
    phase: FaultPhase
    injected_at: AwareDatetime
    progress: float = Field(ge=0, le=1)


class MachineStatus(ContractModel):
    asset_id: str
    name: str
    asset_type: str
    criticality: Criticality
    detector_id: str
    location: str
    placement: Placement
    status: HealthStatus
    risk_level: RiskLevel | None
    risk_score: float | None
    latest_values: dict[str, ReadingValue] | None
    last_reading_at: AwareDatetime | None
    chart_fields: list[str]
    active_incident: IncidentBrief | None
    simulated_fault: FaultInfo | None
    history: list[HistoryPoint]


class RackStatus(ContractModel):
    rack_id: str
    hall_id: str
    row: str
    label: str
    x: float
    y: float
    width: float
    depth: float
    status: HealthStatus
    reasons: list[str]
    cooled_by: list[str]
    machine_ids: list[str]
    open_incident_ids: list[str]


class HallMap(ContractModel):
    hall_id: str
    name: str
    kind: Literal["data_hall", "plant_room"]
    width: float
    depth: float
    status: HealthStatus
    racks: list[RackStatus]
    machines: list[MachineStatus]


class FleetSummary(ContractModel):
    machines: int
    racks: int
    healthy: int
    warning: int
    critical: int
    no_data: int
    open_incidents: int
    racks_affected: int
    downtime_cost_per_day_at_risk: float
    currency: str
    assumptions_source: str | None


class LiveStatus(ContractModel):
    status: LiveState
    run_id: str | None
    seed: int | None
    tick_seconds: float | None
    started_at: AwareDatetime | None
    stopped_at: AwareDatetime | None
    ticks: int
    auto_investigate: bool
    active_faults: list[FaultInfo]


class FleetMap(ContractModel):
    site_name: str
    grid_unit: str
    generated_at: AwareDatetime
    live: LiveStatus
    summary: FleetSummary
    halls: list[HallMap]


class FleetStatus(ContractModel):
    generated_at: AwareDatetime
    live: LiveStatus
    summary: FleetSummary
    machines: list[MachineStatus]


class RackDetail(RackStatus):
    machines: list[MachineStatus]
    cooling_units: list[MachineStatus]
    incidents: list[IncidentSummary]


class LiveStartRequest(ContractModel):
    tick_seconds: float | None = Field(default=None, ge=0.2, le=10)
    seed: int = Field(default=42, ge=0)


class FaultRequest(ContractModel):
    count: int = Field(default=3, ge=1, le=10)
    asset_ids: list[str] | None = Field(default=None, min_length=1, max_length=10)


class FaultResponse(ContractModel):
    injected: list[FaultInfo]
    live: LiveStatus


class ClearResponse(ContractModel):
    readings_deleted: int
    predictions_deleted: int
    incidents_deleted: int
    faults_cleared: int
    simulations_reset: int
    live: LiveStatus
