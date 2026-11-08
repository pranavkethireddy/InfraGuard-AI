export type RepairOption = 'fix_now' | 'wait_for_window' | 'buy_time';
export interface WorkOrderCost { labor: number; parts: number; mitigation: number; total: number }
export interface OpsWorkOrder {
  work_order_id: string; kind: 'repair' | 'routine'; title: string; site_id: string; hall_id: string;
  asset_id: string | null; incident_id: string | null; technician_id: string;
  status: 'scheduled' | 'traveling' | 'in_progress' | 'paused' | 'done'; option: RepairOption | null; mitigation_active: boolean;
  hours_total: number; hours_done: number; progress: number; eta_minutes: number | null;
  scheduled_start: string | null; created_at: string; completed_at: string | null;
  displaced_work_order_id: string | null; cost: WorkOrderCost | null;
}
export interface Technician {
  technician_id: string; name: string; role: string; site_id: string; skills: string[];
  rate_per_hour: number; status: 'idle' | 'traveling' | 'working'; location_hall_id: string;
  current_work_order: OpsWorkOrder | null; queued_work_order_ids: string[];
}
export interface TechniciansResponse { demo_time: string; demo_minutes_per_tick: number; technicians: Technician[]; work_orders: OpsWorkOrder[]; assumptions_source: string }
export interface CurvePoint { hour: number; value: number | null; power_state: 'on' | 'at_risk' | 'off' }
export interface OptionCosts { labor: number; parts: number; downtime_or_lost_revenue: number; mitigation: number; displaced_work: number; total: number }
export interface WhatIfOption {
  option: RepairOption; label: string; description: string; technician_id: string | null; technician_name: string | null;
  displaces: string | null; start_in_hours: number | null; done_in_hours: number | null;
  shutdown_at_hours: number | null; downtime_hours: number | null; costs: OptionCosts; risk_note: string | null; curve: CurvePoint[] | null;
}
export interface WhatIfResponse {
  incident_id: string; asset_id: string; asset_name: string; site_id: string; generated_at: string; demo_time: string;
  metric: string | null; unit: string | null; current_value: number | null; trend_per_hour: number | null;
  shutdown_threshold: number | null; shutdown_in_hours: number | null;
  window: { kind: 'maintenance_window' | 'curtailment'; label: string; starts_in_hours: number; ends_in_hours: number; breakeven_usd_per_mwh?: number | null };
  options: WhatIfOption[]; recommended: RepairOption | null; reason: string; savings_vs_worst: number | null; assumptions_source: string;
}
export interface DispatchRequest { incident_id: string; option: RepairOption; technician_id?: string }
export interface DispatchResponse { work_order: OpsWorkOrder; technician: Technician; displaced: OpsWorkOrder | null }
export interface PlanItem {
  incident_id: string; asset_id: string; asset_name: string; title: string; risk_level: 'low' | 'medium' | 'high'; status: 'ready' | 'waiting_for_technician' | 'dispatched';
  recommended_option: RepairOption | null; technician_id: string | null; technician_name: string | null;
  move_from: string | null; action: string; savings: number | null; repair_hours: number | null;
  savings_per_tech_hour: number | null; work_order_id: string | null;
}
export interface PlanResponse { site_id: string; demo_time: string; items: PlanItem[]; total_savings: number; assumptions_source: string }
export interface LearningCase {
  case_id: string; site_id: string; asset_id: string; asset_type: string; detector_id: string;
  symptom: string; cause: string | null; fix: string; repair_hours: number; cost: number;
  outcome: 'fixed_before_failure' | 'fixed_after_shutdown' | 'resolved_by_operator'; learned_at: string; source: 'technician' | 'operator';
}
export interface LearningCases { items: LearningCase[]; total: number }
export interface LearningRow {
  asset_type: string; symptom: string; cases: number; sites_seen: string[]; shared_with_sites: string[];
  avg_repair_hours: number | null; avg_cost: number | null; fixed_before_failure_pct: number | null;
  best_fix: string | null; last_learned_at: string | null;
}
export interface LearningMatrix { total_cases: number; rows: LearningRow[] }