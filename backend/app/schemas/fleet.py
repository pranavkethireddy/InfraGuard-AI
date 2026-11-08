"""Fleet view: floor map, rack status, machine status and the live demo controls."""

from typing import Literal

from pydantic import AwareDatetime, Field

from .common import ContractModel, Criticality, InvestigationStatus, ReadingValue, RiskLevel
from .incidents import FailureMode, IncidentSummary

# critical: unresolved high-risk incident or latest risk high; warning: medium risk, any other unresolved
# incident, or (racks) a cooling unit serving the rack is not healthy; healthy: latest risk low; no_data: no readings.
HealthStatus = Literal["healthy", "warning", "critical", "no_data"]
LiveState = Literal["running", "stopped"]
FaultKind = Literal["cooling_failure", "drive_degradation", "machine_overstrain", "fan_failure", "hashboard_failure",
                    "gpu_fault", "psu_failure", "server_crash", "memory_fault", "nic_failure", "server_fan_failure"]
SiteId = Literal["datacenter", "mining"]
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


PowerState = Literal["on", "at_risk", "off"]


class WorkOrderBrief(ContractModel):
    work_order_id: str
    technician_id: str
    technician_name: str
    status: Literal["scheduled", "paged", "traveling", "in_progress", "awaiting_confirmation", "paused", "done"]
    option: Literal["fix_now", "wait_for_window", "buy_time"] | None
    progress: float = Field(ge=0, le=1)
    eta_minutes: float | None


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
    # Additive: off = thermal shutdown (no readings while off); at_risk = projected to shut down within
    # the projection horizon; shutdown_eta_minutes is demo minutes from the observed trend.
    power_state: PowerState = "on"
    power_reason: str | None = None
    shutdown_eta_minutes: float | None = None
    work_order: WorkOrderBrief | None = None


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
    power_state: PowerState = "on"
    shutdown_eta_minutes: float | None = None


class HallMap(ContractModel):
    hall_id: str
    name: str
    kind: Literal["data_hall", "plant_room", "mining_container"]
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
    # Business case over unresolved incidents (additive): what they cost if they fail vs fixing them now.
    machines_powered_off: int = 0
    machines_at_risk_of_shutdown: int = 0
    cost_if_all_fail: float = 0.0
    cost_to_fix_all_now: float = 0.0
    savings_if_fixed_now: float = 0.0


class SiteMetric(ContractModel):
    """One headline number for the site's metric tiles. source says where the number comes from."""

    key: str
    label: str
    value: float | None
    unit: str
    source: str


class ChaosRequest(ContractModel):
    enabled: bool


class ChaosStatus(ContractModel):
    """Demo chaos mode: random GPU server faults and priority changes, never touching protected technicians."""
    enabled: bool
    protected_technicians: list[str]
    active_faults: list[str]


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


class GpuStatus(ContractModel):
    index: int
    temp_c: float | None
    clock_pct: float | None
    # throttling: hot enough that the GPU slowed its clock; offline: dropped off the bus or server down.
    status: Literal["ok", "throttling", "offline", "no_data"]
    throttle_c: float


class JobStatus(ContractModel):
    """One synchronous GPU job across a row's servers: the slowest GPU sets its pace."""

    job_id: str
    name: str
    row: str
    hall_id: str
    server_ids: list[str]
    gpus: int
    gpus_running: int
    pace_pct: float
    gpus_throttled: int
    servers_down: list[str]
    # Compute paid for but not delivered right now: idle GPUs plus the slowdown of the running ones.
    lost_usd_per_hour: float
    gpu_hour_usd: float
    reasons: list[str]
    assumptions_source: str


class ServerDetail(ContractModel):
    machine: MachineStatus
    rack_id: str
    inlet_temp_c: float | None
    online: bool | None
    psus_ok: int | None
    psus_total: int
    ecc_errors: int | None
    power_w: float | None
    gpus: list[GpuStatus]
    job: JobStatus | None
    cooled_by: list[MachineStatus]


class FleetMap(ContractModel):
    site_id: SiteId = "datacenter"
    site_name: str
    grid_unit: str
    generated_at: AwareDatetime
    live: LiveStatus
    summary: FleetSummary
    site_metrics: list[SiteMetric] = []
    halls: list[HallMap]
    jobs: list[JobStatus] = []


class FleetStatus(ContractModel):
    site_id: SiteId = "datacenter"
    generated_at: AwareDatetime
    live: LiveStatus
    summary: FleetSummary
    site_metrics: list[SiteMetric] = []
    machines: list[MachineStatus]


class SiteInfo(ContractModel):
    site_id: SiteId
    name: str
    machines: int
    racks: int
    summary: FleetSummary
    site_metrics: list[SiteMetric]


class SitesResponse(ContractModel):
    generated_at: AwareDatetime
    live: LiveStatus
    sites: list[SiteInfo]


class RackDetail(RackStatus):
    machines: list[MachineStatus]
    server_ids: list[str] = []
    cooling_units: list[MachineStatus]
    incidents: list[IncidentSummary]


class LiveStartRequest(ContractModel):
    tick_seconds: float | None = Field(default=None, ge=0.2, le=10)
    seed: int = Field(default=42, ge=0)


class FaultRequest(ContractModel):
    count: int = Field(default=3, ge=1, le=10)
    # Only pick machines from this site when asset_ids is not given; None picks from both sites.
    site: SiteId | None = None
    asset_ids: list[str] | None = Field(default=None, min_length=1, max_length=10)
    # Which fault to inject (e.g. gpu_fault = one GPU fails, server_crash = the whole server goes down).
    # Must suit every chosen machine's type; None picks one per machine.
    kind: FaultKind | None = None


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


ComponentKind = Literal["gpu", "cpu", "dimm", "fan", "psu", "nic", "nvme", "bmc"]
ComponentStatus = Literal["ok", "warning", "failed", "offline"]


class Component(ContractModel):
    """One part inside a GPU server, from the server's latest reading."""
    component_id: str
    kind: ComponentKind
    name: str
    status: ComponentStatus
    metrics: dict[str, float]
    note: str | None = None


class ServerComponents(ContractModel):
    server_id: str
    observed_at: AwareDatetime | None
    components: list[Component]


class ComponentHistoryPoint(ContractModel):
    observed_at: AwareDatetime
    status: ComponentStatus
    metrics: dict[str, float]


class ComponentDetail(ContractModel):
    server_id: str
    component: Component
    history: list[ComponentHistoryPoint]
    # The server's matched failure playbook when this part is not ok.
    failure_mode: FailureMode | None = None
