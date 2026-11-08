"""Operations: technicians, work orders, repair plan, what-if futures and the learning matrix."""

from typing import Literal

from pydantic import AwareDatetime, Field

from .common import ContractModel, RiskLevel

TechStatus = Literal["idle", "traveling", "working"]
WorkKind = Literal["repair", "routine"]
WorkStatus = Literal["scheduled", "traveling", "in_progress", "paused", "done"]
OptionId = Literal["fix_now", "wait_for_window", "buy_time"]
PowerState = Literal["on", "at_risk", "off"]


class WorkOrderCost(ContractModel):
    labor: float
    parts: float
    mitigation: float
    total: float


class WorkOrder(ContractModel):
    work_order_id: str
    kind: WorkKind
    title: str
    site_id: str
    hall_id: str
    asset_id: str | None
    incident_id: str | None
    technician_id: str
    status: WorkStatus
    option: OptionId | None
    mitigation_active: bool
    hours_total: float
    hours_done: float
    progress: float = Field(ge=0, le=1)
    # Demo minutes until done (travel + remaining work), or until a scheduled start.
    eta_minutes: float | None
    scheduled_start: AwareDatetime | None
    created_at: AwareDatetime
    completed_at: AwareDatetime | None
    displaced_work_order_id: str | None
    cost: WorkOrderCost | None


class Technician(ContractModel):
    technician_id: str
    name: str
    role: str
    site_id: str
    skills: list[str]
    rate_per_hour: float
    status: TechStatus
    location_hall_id: str
    current_work_order: WorkOrder | None
    queued_work_order_ids: list[str]


class TechniciansResponse(ContractModel):
    demo_time: AwareDatetime
    demo_minutes_per_tick: float
    technicians: list[Technician]
    work_orders: list[WorkOrder]
    assumptions_source: str


class Window(ContractModel):
    kind: Literal["maintenance_window", "curtailment"]
    label: str
    starts_in_hours: float
    ends_in_hours: float
    # Mining only: power price at which mining stops paying, from hashprice and miner power.
    breakeven_usd_per_mwh: float | None = None


class CurvePoint(ContractModel):
    hour: float
    value: float | None
    power_state: PowerState


class OptionCosts(ContractModel):
    labor: float
    parts: float
    downtime_or_lost_revenue: float
    mitigation: float
    displaced_work: float
    total: float


class WhatIfOption(ContractModel):
    option: OptionId
    label: str
    description: str
    technician_id: str | None
    technician_name: str | None
    # Title of the job the technician is pulled off, if any.
    displaces: str | None
    start_in_hours: float | None
    done_in_hours: float | None
    shutdown_at_hours: float | None
    downtime_hours: float
    costs: OptionCosts
    risk_note: str | None
    curve: list[CurvePoint]


class WhatIf(ContractModel):
    incident_id: str
    asset_id: str
    asset_name: str
    site_id: str
    generated_at: AwareDatetime
    demo_time: AwareDatetime
    metric: str | None
    unit: str | None
    current_value: float | None
    trend_per_hour: float | None
    shutdown_threshold: float | None
    # With no action: demo hours until the machine (or the racks it cools) shuts down; None = no thermal path.
    shutdown_in_hours: float | None
    window: Window
    options: list[WhatIfOption]
    recommended: OptionId
    reason: str
    savings_vs_worst: float
    assumptions_source: str


class PlanItem(ContractModel):
    incident_id: str
    asset_id: str
    asset_name: str
    title: str
    risk_level: RiskLevel
    status: Literal["ready", "waiting_for_technician", "dispatched"]
    recommended_option: OptionId
    technician_id: str | None
    technician_name: str | None
    move_from: str | None
    action: str
    savings: float
    repair_hours: float
    savings_per_tech_hour: float
    work_order_id: str | None


class PlanResponse(ContractModel):
    site_id: str
    demo_time: AwareDatetime
    items: list[PlanItem]
    total_savings: float
    assumptions_source: str


class DispatchRequest(ContractModel):
    incident_id: str
    # None uses the what-if recommendation.
    option: OptionId | None = None
    # None picks the best qualified technician (may move one off routine work).
    technician_id: str | None = None


class DispatchResponse(ContractModel):
    work_order: WorkOrder
    technician: Technician
    displaced: WorkOrder | None


class LearnedCase(ContractModel):
    case_id: str
    site_id: str
    asset_id: str
    asset_type: str
    detector_id: str
    symptom: str
    cause: str | None
    fix: str
    repair_hours: float
    cost: float
    outcome: Literal["fixed_before_failure", "fixed_after_shutdown", "resolved_by_operator"]
    learned_at: AwareDatetime
    source: Literal["technician", "operator"]


class MatrixRow(ContractModel):
    asset_type: str
    symptom: str
    cases: int
    sites_seen: list[str]
    # Every site that has this equipment type and so gets this knowledge.
    shared_with_sites: list[str]
    avg_repair_hours: float
    avg_cost: float
    fixed_before_failure_pct: float
    best_fix: str
    last_learned_at: AwareDatetime


class LearningMatrix(ContractModel):
    total_cases: int
    rows: list[MatrixRow]


class LearnedCases(ContractModel):
    items: list[LearnedCase]
    total: int
