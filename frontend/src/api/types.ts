// Response contracts from the InfraGuard backend (see contracts/fixtures in the main repo).
// Risk, score, cost and priority values are server-provided; the UI only displays them.
export type RiskLevel = "low" | "medium" | "high";
export type DataOrigin = "simulated" | "observed";
export type ScoreKind = "heuristic" | "model_score" | "calibrated_probability";
export type IncidentStatus = "open" | "acknowledged" | "resolved";
export type AssetType = "cooling_unit" | "industrial_machine" | "storage_drive" | "asic_miner" | "mining_container";
export type ExplanationSource = "rule" | "template" | "rag" | "agent";

export interface Paginated<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Asset {
  asset_id: string;
  name: string;
  asset_type: AssetType;
  location: string;
  criticality: string;
  compatible_detector: string | null;
  data_origin: DataOrigin;
  current_risk_level: RiskLevel | null;
  active_incident_id: string | null;
  last_reading_at: string | null;
}

export interface ImpactAssumptions {
  currency: string;
  estimated_downtime_hours: number | null;
  cost_per_hour: number | null;
  estimated_repair_cost: number | null;
  assumptions_source: string | null;
}

export interface AssetDetail extends Asset {
  impact_assumptions: ImpactAssumptions | null;
}

/** Reading values are domain-specific (e.g. temperature_c/fan_speed_rpm for cooling units). */
export type ReadingValues = Record<string, number | string | boolean | null>;

export interface Reading {
  observed_at: string;
  values: ReadingValues;
  data_origin: DataOrigin;
}

export interface ReadingsPage {
  asset_id: string;
  start: string | null;
  end: string | null;
  items: Reading[];
  total: number;
  limit: number;
}

export interface Evidence {
  type: string;
  field: string;
  value: number | string | null;
  threshold: number | null;
  unit: string | null;
  consecutive_readings: number | null;
}

export interface MaintenanceSource {
  record_id: string;
  asset_id: string;
  recorded_at: string;
  source_name: string;
  excerpt: string;
  score: number | null;
}

export interface Prediction {
  prediction_id: string;
  asset_id: string;
  detector_id: string;
  observed_at: string;
  generated_at: string;
  data_origin: DataOrigin;
  model_name: string;
  model_version: string;
  target: string;
  risk_score: number;
  score_kind: ScoreKind;
  risk_level: RiskLevel;
  prediction_horizon_hours: number | null;
  explanation: string | null;
  explanation_source: ExplanationSource;
  evidence: Evidence[];
  maintenance_sources: MaintenanceSource[];
  limitations: string[];
  incident_id: string | null;
  simulation_id: string | null;
}

export interface IncidentSummary {
  incident_id: string;
  asset_id: string;
  detector_id: string;
  status: IncidentStatus;
  risk_level: RiskLevel;
  score_kind: ScoreKind;
  data_origin: DataOrigin;
  title: string;
  opened_at: string;
  last_seen_at: string | null;
  acknowledged_at: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
  prediction_count: number;
  simulation_id: string | null;
  priority_index: number | null;
  investigation_status?: import('./fleet-types').InvestigationStatus | null;
}

export interface Impact extends ImpactAssumptions {
  estimated_downtime_cost: number | null;
  estimated_total_impact: number | null;
  /** Optional backend demo assumptions (newer API). Displayed as returned, never computed. */
  cost_per_day?: number | null;
  estimated_repair_hours?: number | null;
  planned_repair_cost?: number | null;
  cost_if_it_fails?: number | null;
  cost_to_fix_now?: number | null;
  savings_if_fixed_now?: number | null;
  return_on_repair?: number | null;
}

export interface IncidentNote {
  note: string;
  status: IncidentStatus;
  created_at: string;
}

export interface IncidentDetail extends IncidentSummary {
  latest_prediction: Prediction | null;
  evidence: Evidence[];
  maintenance_sources: MaintenanceSource[];
  explanation: string | null;
  explanation_source: ExplanationSource | null;
  recommended_actions: string[];
  impact: Impact | null;
  priority_weights: Record<string, number> | null;
  notes: IncidentNote[];
  /** Optional: tool steps reported by the backend investigation agent. */
  agent_steps?: AgentStep[] | null;
  problem?: string | null;
  likely_cause?: string | null;
  work_order_id?: string | null;
}

export interface AgentStep {
  tool: string;
  summary: string;
}

export interface IncidentPatch {
  status: "acknowledged" | "resolved";
  note: string | null;
}

export type Scenario = "normal" | "cooling_anomaly";
export interface SimulationRequest {
  scenario: Scenario;
  asset_id: string;
  seed: number;
}
export interface Simulation {
  simulation_id: string;
  scenario: Scenario;
  asset_id: string;
  seed: number;
  status: "running" | "completed" | "reset";
  data_origin: "simulated";
  started_at: string;
  completed_at: string | null;
  tick_seconds: number;
  samples_total: number;
  samples_emitted: number;
}
export interface SimulationReset {
  simulation_id: string;
  status: "reset";
  readings_deleted: number;
  predictions_deleted: number;
  incidents_resolved: number;
}

export interface ConfusionMatrix {
  tp: number;
  fp: number;
  tn: number;
  fn: number;
}
export interface MetricsBaseline {
  name: string;
  pr_auc: number | null;
  f1: number | null;
}
export interface EvaluationMetrics {
  split: string;
  evaluated_at: string;
  dataset_version: string;
  seed: number | null;
  n: number;
  positives: number;
  threshold: number | null;
  threshold_selection: string | null;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  pr_auc: number | null;
  roc_auc: number | null;
  brier: number | null;
  calibrated: boolean;
  confusion_matrix: ConfusionMatrix | null;
  baseline: MetricsBaseline | null;
  metrics_file: string | null;
}

export interface RuleConfig {
  temperature_threshold_c?: number;
  consecutive_readings?: number;
  cooldown_readings?: number;
  [key: string]: number | string | boolean | null | undefined;
}

export interface DetectorModel {
  detector_id: string;
  model_name: string;
  model_version: string;
  kind: "rule" | "ml";
  asset_types: AssetType[];
  score_kind: ScoreKind;
  target: string;
  prediction_horizon_hours: number | null;
  input_fields: { name: string; unit: string | null; required: boolean }[];
  risk_thresholds: Record<string, number> | null;
  rule_config: RuleConfig | null;
  status: "available" | "unavailable";
  evaluation_status: "not_applicable" | "not_evaluated" | "evaluated";
  metrics: EvaluationMetrics | null;
  source_dataset: string | null;
  model_card_url: string | null;
  limitations: string[];
}

export interface ErrorEnvelope {
  error: { code: string; message: string; details: unknown; request_id: string | null };
}
