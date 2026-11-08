import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Regression: a completed run must survive route changes / reload until reset (live, mocked HTTP).
const h = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock("@/api/client", async (orig) => {
  const m = await orig<typeof import("@/api/client")>();
  return { ...m, DATA_MODE: "live", api: m.createLiveClient("http://t/api/v1", (...a) => h.fetch(...a)) };
});

import { SimulatePage } from "@/pages/SimulatePage";
import { pickRecoverableSimulation } from "@/api/queries";
import { fixtures } from "@/api/fixtures";
import type { Simulation } from "@/api/types";

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status, headers: { "Content-Type": "application/json" } });
const page = <T,>(items: T[]) => ({ items, total: items.length, limit: 50, offset: 0 });
const run = (id: string, status: Simulation["status"]): Simulation => ({ ...fixtures.simulationStatus, simulation_id: id, status, samples_emitted: 30, completed_at: status === "running" ? null : "2026-11-07T20:01:00Z" });

let runs: Simulation[] = [];
let readingsCalls = 0;
function backend() {
  h.fetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = String(url).replace("http://t/api/v1", "").split("?")[0]!;
    const key = `${init?.method ?? "GET"} ${path}`;
    if (key === "GET /assets") return json(fixtures.assetsList);
    if (key === "GET /models") return json(fixtures.modelsList);
    if (key === "GET /assets/cooling-01/readings") { readingsCalls += 1; return json(fixtures.assetReadings); }
    if (key === "GET /simulations") return json(page(runs));
    const m = path.match(/^\/simulations\/([^/]+)(\/reset)?$/);
    if (m) {
      const r = runs.find((x) => x.simulation_id === m[1]);
      if (!r) return json({ error: { code: "not_found", message: "nf", details: null, request_id: "r" } }, 404);
      if (m[2] && init?.method === "POST") { r.status = "reset"; return json({ ...fixtures.simulationReset, simulation_id: r.simulation_id }); }
      return json(r);
    }
    return json({ error: { code: "no_route", message: "no", details: null, request_id: null } }, 404);
  });
}
const client = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });
const mount = (qc: QueryClient) => render(<QueryClientProvider client={qc}><SimulatePage /></QueryClientProvider>);
const resetBtn = () => screen.queryByRole("button", { name: "Reset simulation" });

beforeEach(() => { h.fetch.mockReset(); readingsCalls = 0; runs = [run("sim-new", "completed"), run("sim-old", "reset")]; backend(); });

describe("completed simulation recovery", () => {
  it("picks running first, else newest completed, never reset", () => {
    expect(pickRecoverableSimulation([run("a", "completed"), run("b", "running")])?.simulation_id).toBe("b");
    expect(pickRecoverableSimulation([run("a", "reset"), run("b", "completed"), run("c", "completed")])?.simulation_id).toBe("b");
    expect(pickRecoverableSimulation([run("a", "reset")])).toBeNull();
  });

  it("completed -> incident -> return keeps status/readings/Reset, then reset clears it", async () => {
    const qc = client();
    const first = mount(qc);
    expect(await screen.findByText("Status: completed")).toBeInTheDocument();
    first.unmount(); // navigate to the incident page
    mount(qc);       // return to /simulate
    expect(await screen.findByText("Status: completed")).toBeInTheDocument();
    expect(screen.getByText("sim-new")).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: /Temperature/ })).toBeInTheDocument();
    const before = readingsCalls;
    fireEvent.click(resetBtn()!);
    expect(await screen.findByText("Readings deleted")).toBeInTheDocument();
    expect(resetBtn()).toBeNull();
    await waitFor(() => expect(readingsCalls).toBeGreaterThan(before));
    expect(screen.queryByText("Status: completed")).toBeNull();
  });

  it("recovers a completed run after a full reload", async () => {
    mount(client());
    expect(await screen.findByText("Status: completed")).toBeInTheDocument();
    expect(resetBtn()).toBeEnabled();
  });

  it("does not resurrect the reset run after remount", async () => {
    const qc = client();
    const first = mount(qc);
    fireEvent.click(await screen.findByRole("button", { name: "Reset simulation" }));
    expect(await screen.findByText("Readings deleted")).toBeInTheDocument();
    first.unmount();
    mount(qc);
    expect(await screen.findByText("No running or completed simulation for this asset.")).toBeInTheDocument();
    expect(resetBtn()).toBeNull();
    mount(client()).unmount();
  });

  it("disables start while status recovery is loading", async () => {
    h.fetch.mockImplementation(async (url: string) => {
      const u = String(url);
      if (u.includes("/assets?limit=100")) return json(fixtures.assetsList);
      if (u.includes("/models")) return json(fixtures.modelsList);
      return new Promise<Response>(() => {});
    });
    mount(client());
    expect(await screen.findByText("Checking for a running simulation…", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start simulation/i })).toBeDisabled();
  });
});
