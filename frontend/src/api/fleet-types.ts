import type { IncidentSummary, ReadingValues, RiskLevel } from './types';
import type { WorkStatus } from './ops-types';

export type SiteId = 'datacenter' | 'mining';
export type HealthStatus = 'healthy' | 'warning' | 'critical' | 'no_data';
export type InvestigationStatus = 'queued' | 'running' | 'completed' | 'failed';
export type PowerState = 'on' | 'at_risk' | 'off';
export interface WorkOrder {
  work_order_id: string; technician_id: string; technician_name: string;
  status: WorkStatus;
  option: 'fix_now' | 'wait_for_window' | 'buy_time' | null;
  progress: number; eta_minutes: number | null;
}
export interface Placement { hall_id: string; row: string | null; rack_id: string | null; slot: number | null; x: number; y: number }
export interface HistoryPoint { observed_at: string; values: ReadingValues }
export interface IncidentBrief {
  incident_id: string; title: string; status: 'open' | 'acknowledged'; risk_level: RiskLevel;
  opened_at: string; estimated_total_impact: number | null; cost_per_day: number | null;
  investigation_status: InvestigationStatus | null;
}
export type FaultKind = 'cooling_failure' | 'drive_degradation' | 'machine_overstrain' | 'fan_failure' | 'hashboard_failure' | 'gpu_fault' | 'psu_failure' | 'server_crash' | 'memory_fault' | 'nic_failure' | 'server_fan_failure';
export interface FaultInfo {
  asset_id: string; kind: FaultKind;
  phase: 'ramping' | 'holding' | 'recovering' | 'ended'; injected_at: string; progress: number;
}
export interface MachineStatus {
  asset_id: string; name: string; asset_type: string; criticality: string; detector_id: string; location: string;
  placement: Placement; status: HealthStatus; risk_level: RiskLevel | null; risk_score: number | null;
  latest_values: ReadingValues | null; last_reading_at: string | null; chart_fields: string[];
  active_incident: IncidentBrief | null; simulated_fault: FaultInfo | null; history: HistoryPoint[];
  power_state?: PowerState; power_reason?: string | null; shutdown_eta_minutes?: number | null; work_order?: WorkOrder | null;
}
export interface RackStatus {
  rack_id: string; hall_id: string; row: string; label: string; x: number; y: number; width: number; depth: number;
  status: HealthStatus; reasons: string[]; cooled_by: string[]; machine_ids: string[]; open_incident_ids: string[];
  power_state?: PowerState; power_reason?: string | null; shutdown_eta_minutes?: number | null;
}
export interface HallMap {
  hall_id: string; name: string; kind: 'data_hall' | 'plant_room' | 'mining_container'; width: number; depth: number;
  status: HealthStatus; racks: RackStatus[]; machines: MachineStatus[];
}
export interface FleetSummary {
  machines: number; racks: number; healthy: number; warning: number; critical: number; no_data: number;
  open_incidents: number; racks_affected: number; downtime_cost_per_day_at_risk: number; currency: string;
  assumptions_source: string | null; cost_if_all_fail: number; cost_to_fix_all_now: number; savings_if_fixed_now: number;
  machines_powered_off?: number; machines_at_risk_of_shutdown?: number;
}
export interface SiteMetric { key: string; label: string; value: number | null; unit: string; source: string }
export interface LiveStatus {
  status: 'running' | 'stopped'; run_id: string | null; seed: number | null; tick_seconds: number | null;
  started_at: string | null; stopped_at: string | null; ticks: number; auto_investigate: boolean; active_faults: FaultInfo[];
}
export interface FleetMap { site_id: SiteId; site_name: string; grid_unit: string; generated_at: string; live: LiveStatus; summary: FleetSummary; site_metrics: SiteMetric[]; halls: HallMap[]; jobs?: GpuJob[] }
export interface FleetStatus { site_id: SiteId; generated_at: string; live: LiveStatus; summary: FleetSummary; site_metrics: SiteMetric[]; machines: MachineStatus[] }
export interface SiteInfo { site_id: SiteId; name: string; machines: number; racks: number; summary: FleetSummary; site_metrics: SiteMetric[] }
export interface SitesResponse { generated_at: string; live: LiveStatus; sites: SiteInfo[] }
export interface RackDetail extends RackStatus { machines: MachineStatus[]; cooling_units: MachineStatus[]; incidents: IncidentSummary[]; server_ids?: string[] }
export interface LiveStartRequest { seed?: number; tick_seconds?: number }
export interface ChaosStatus { enabled: boolean; protected_technicians: string[]; active_faults: string[] }
export interface FaultRequest { count?: number; site?: SiteId | null; asset_ids?: string[] | null; kind?: FaultKind | null }
export interface FaultResponse { injected: FaultInfo[]; live: LiveStatus }
export interface ClearResponse { readings_deleted: number; predictions_deleted: number; incidents_deleted: number; faults_cleared: number; simulations_reset: number; live: LiveStatus }
export interface GpuJob {
  job_id: string; name: string; row: string; hall_id: string; server_ids: string[];
  gpus: number; gpus_running: number; pace_pct: number | null; gpus_throttled: number;
  servers_down: string[]; lost_usd_per_hour: number | null; gpu_hour_usd: number;
  reasons: string[]; assumptions_source: string;
}
export interface GpuStatus { index: number; temp_c: number | null; clock_pct: number | null; status: 'ok' | 'throttling' | 'offline' | 'no_data'; throttle_c: number }
export interface ServerDetail {
  machine: MachineStatus; rack_id: string; inlet_temp_c: number | null; online: boolean | null;
  psus_ok: number | null; psus_total: number; ecc_errors: number | null; power_w: number | null;
  gpus: GpuStatus[]; job: GpuJob | null; cooled_by: MachineStatus[];
}