"""Operations: technicians, work orders, repair plan, what-if futures and the learning matrix."""

from typing import Literal

from pydantic import AwareDatetime, Field

from .common import ContractModel, RiskLevel

TechStatus = Literal["idle", "traveling", "working"]
WorkKind = Literal["repair", "routine"]
# paged: sent to a technician's pager, waiting for them to accept (device-controlled technicians only).
# awaiting_confirmation: the planned hours are used up; the technician confirms "done" on the pager.
WorkStatus = Literal["scheduled", "paged", "traveling", "in_progress", "awaiting_confirmation", "paused", "done"]
OptionId = Literal["fix_now", "wait_for_window", "buy_time"]
PowerState = Literal["on", "at_risk", "off"]


class FloorPoint(ContractModel):
    """A point on the site floor plan (GET /ops/floor), in floor cells. hall_id is None in the corridor."""

    x: float
    y: float
    hall_id: str | None


class FloorHall(ContractModel):
    hall_id: str
    name: str
    # Hall origin on the site floor: a hall-local point (x, y) from the fleet map is at (x + this.x, y + this.y).
    x: float
    y: float
    width: float
    depth: float
    door: FloorPoint


class FloorPlan(ContractModel):
    site_id: str
    width: float
    depth: float
    corridor_y: float
    lane_offset: float
    grid_unit: str
    halls: list[FloorHall]


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
    # Where the work happens on the floor plan (the aisle in front of the rack, or beside the unit).
    spot: FloorPoint | None = None
    asset_name: str | None = None


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
    # Live position on the floor plan and the waypoints still to walk (empty when not walking).
    position: FloorPoint | None = None
    path: list[FloorPoint] = []
    walking_minutes_left: float | None = None
    # True while a pager (e.g. an iPad) has claimed this technician: they accept and finish jobs themselves.
    device_controlled: bool = False


class TechniciansResponse(ContractModel):
    demo_time: AwareDatetime
    demo_minutes_per_tick: float
    # New incidents are sent to the closest qualified technician automatically.
    auto_dispatch: bool = False
    walk_cells_per_demo_minute: float = 0.0
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


PagerAction = Literal["accept", "decline", "done"]


class PagerJob(ContractModel):
    work_order: WorkOrder
    asset_id: str | None
    asset_name: str | None
    location: str | None
    incident_id: str | None
    risk_level: RiskLevel | None
    problem: str | None
    likely_cause: str | None
    steps: list[str]
    # Why this technician: e.g. "Closest qualified technician: 1.4 demo minutes away".
    why_you: str
    savings_if_fixed_now: float | None
    cost_per_hour_while_down: float | None
    walking_minutes_left: float | None
    actions: list[PagerAction]


class PagerView(ContractModel):
    technician: Technician
    job: PagerJob | None
    queue: list[WorkOrder]
    demo_time: AwareDatetime
    # Increases on every change; the stream sends a new view only when it changes.
    version: int


class PagerActionRequest(ContractModel):
    action: PagerAction
    work_order_id: str


class AutoDispatchRequest(ContractModel):
    enabled: bool
