import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { createFixtureClient, createLiveClient, resolveDataMode } from "@/api/client";
import { SIM_POLL_MS, simulationPollInterval } from "@/api/queries";
import { horizonLabel, ModelCard } from "@/components/ModelCard";
import { EquipmentTable } from "@/components/tables";
import { explanationSourceLabel, ImpactLedger } from "@/pages/IncidentDetailPage";
import { parseSeed } from "@/pages/SimulatePage";
import type { Asset, DetectorModel, Impact } from "@/api/types";
// Test-only: approved agent response contract; never served in fixture mode.
import investigatedJson from "@/api/fixtures/contracts/incident.investigate.response.json";
import type { IncidentDetail } from "@/api/types";
import type { Widen } from "@/api/fixtures";
const _check: Widen<IncidentDetail> = investigatedJson;
void _check;
const investigated = investigatedJson as unknown as IncidentDetail;
import drive from "./examples/storage-drive.example.json";

describe("data mode", () => {
  it("explicit VITE_DATA_MODE wins over the target default", () => {
    expect(resolveDataMode("fixture", "live")).toBe("fixture");
    expect(resolveDataMode("live", "fixture")).toBe("live");
    expect(resolveDataMode(undefined, "live")).toBe("live");
    expect(resolveDataMode("bogus", "live")).toBe("live");
  });
});

describe("simulation rules", () => {
  it("seed must be a whole number >= 0", () => {
    expect(parseSeed("0")).toBe(0);
    expect(parseSeed("42")).toBe(42);
    expect(parseSeed("-1")).toBeNull();
    expect(parseSeed("1.5")).toBeNull();
    expect(parseSeed("")).toBeNull();
  });
  it("polls every 2 seconds only while running", () => {
    expect(SIM_POLL_MS).toBe(2000);
    expect(simulationPollInterval("running")).toBe(2000);
    expect(simulationPollInterval("completed")).toBe(false);
    expect(simulationPollInterval("reset")).toBe(false);
  });
});

describe("investigate client", () => {
  it("POSTs /incidents/{id}/investigate with no body", async () => {
    const f = vi.fn().mockResolvedValue(new Response(JSON.stringify(investigated), { status: 200 }));
    const r = await createLiveClient("http://x/api/v1", f).investigateIncident("inc-demo-001");
    expect(f.mock.calls[0]?.[0]).toBe("http://x/api/v1/incidents/inc-demo-001/investigate");
    expect(f.mock.calls[0]?.[1]).toMatchObject({ method: "POST" });
    expect(f.mock.calls[0]?.[1].body).toBeUndefined();
    expect(r.agent_steps).toEqual(investigated.agent_steps);
  });
  it("is disabled in fixture mode", async () => {
    await expect(createFixtureClient().investigateIncident("inc-demo-001")).rejects.toMatchObject({ code: "fixture_mode" });
  });
});

describe("impact ledger optional fields", () => {
  it("shows backend cost_per_day and estimated_repair_hours as demo assumptions", () => {
    render(<ImpactLedger impact={investigated.impact as Impact} />);
    expect(screen.getByText("Cost per day")).toBeInTheDocument();
    expect(screen.getByText(/288,000/)).toBeInTheDocument();
    expect(screen.getByText("3 h")).toBeInTheDocument();
  });
  it("omits rows when the backend does not send them", () => {
    const { cost_per_day: _a, estimated_repair_hours: _b, ...older } = investigated.impact!;
    render(<ImpactLedger impact={older as Impact} />);
    expect(screen.queryByText("Cost per day")).toBeNull();
  });
});

describe("explanation source labels", () => {
  it("labels agent vs fallback honestly", () => {
    expect(explanationSourceLabel("agent")).toMatch(/AI agent.*human review required/);
    expect(explanationSourceLabel("rag")).toMatch(/Fallback: rag.*agent not used/);
    expect(explanationSourceLabel("template")).toMatch(/Fallback: template.*agent not used/);
  });
});

describe("storage drive shapes", () => {
  it("renders drive-failure-v1 model_score as not a probability with a 30-day horizon", () => {
    render(<ModelCard model={drive.model as DetectorModel} />);
    expect(screen.getAllByText(/Uncalibrated model score — not a probability/).length).toBeGreaterThan(0);
    expect(screen.getByText("720 h (30 days)")).toBeInTheDocument();
    expect(screen.getAllByText("Not evaluated").length).toBeGreaterThan(0);
    expect(horizonLabel(5)).toBe("5 h");
  });
  it("lists a storage_drive asset", () => {
    render(<EquipmentTable assets={[drive.asset as Asset]} />);
    expect(screen.getByText("storage_drive")).toBeInTheDocument();
  });
});
