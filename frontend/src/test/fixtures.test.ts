import { describe, expect, it } from "vitest";
import { fixtures } from "@/api/fixtures";
import evaluatedExample from "@/api/fixtures/contracts/model.evaluated.example.json";

const RISK = [null, "low", "medium", "high"];
const ORIGIN = ["simulated", "observed"];
const SCORE = ["heuristic", "model_score", "calibrated_probability"];
const ASSET_TYPES = ["cooling_unit", "industrial_machine"];

// Runtime half of the fixture compatibility check (literal enums are widened in JSON imports).
describe("contract fixtures", () => {
  it("assets use approved enums", () => {
    for (const a of fixtures.assetsList.items) {
      expect(ASSET_TYPES).toContain(a.asset_type);
      expect(ORIGIN).toContain(a.data_origin);
      expect(RISK).toContain(a.current_risk_level);
    }
    expect(ASSET_TYPES).toContain(fixtures.assetDetail.asset_type);
  });
  it("readings page has no offset and carries asset_id/start/end", () => {
    expect(Object.keys(fixtures.assetReadings).sort()).toEqual(["asset_id", "end", "items", "limit", "start", "total"]);
  });
  it("incidents and models use approved enums", () => {
    for (const i of fixtures.incidentsList.items) {
      expect(["open", "acknowledged", "resolved"]).toContain(i.status);
      expect(SCORE).toContain(i.score_kind);
    }
    for (const m of fixtures.modelsList.items) {
      expect(SCORE).toContain(m.score_kind);
      expect(["available", "unavailable"]).toContain(m.status);
      expect(["not_applicable", "not_evaluated", "evaluated"]).toContain(m.evaluation_status);
      expect(m.metrics).toBeNull();
    }
  });
  it("cooling rule uses consecutive_readings/cooldown_readings keys", () => {
    const rule = fixtures.modelsList.items.find((m) => m.detector_id === "cooling-rule-v1")!;
    expect(rule.rule_config).toMatchObject({ temperature_threshold_c: 32, consecutive_readings: 3, cooldown_readings: 3 });
  });
  it("reset response is counts, not a Simulation", () => {
    expect(fixtures.simulationReset).toEqual({ simulation_id: "sim-demo-001", status: "reset", readings_deleted: 12, predictions_deleted: 12, incidents_resolved: 1 });
  });
  it("evaluated example has structured metrics (test-only)", () => {
    expect(evaluatedExample.metrics.confusion_matrix).toEqual({ tp: 34, fp: 34, tn: 1898, fn: 34 });
    expect(evaluatedExample.metrics.calibrated).toBe(false);
    expect(evaluatedExample.metrics.roc_auc).toBeNull();
  });
});
