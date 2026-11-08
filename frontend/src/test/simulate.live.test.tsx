import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Live mode with mocked HTTP: the real live client runs against a fake backend.
const h = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock("@/api/client", async (orig) => {
  const m = await orig<typeof import("@/api/client")>();
  return { ...m, DATA_MODE: "live", api: m.createLiveClient("http://t/api/v1", (...a) => h.fetch(...a)) };
});

import { SimulatePage } from "@/pages/SimulatePage";
import { fixtures } from "@/api/fixtures";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const err = (status: number, code: string) => json({ error: { code, message: `backend says ${code}`, details: null, request_id: `req-${status}` } }, status);
const page = <T,>(items: T[]) => ({ items, total: items.length, limit: 50, offset: 0 });
const sim = (over: Record<string, unknown> = {}) => ({ ...fixtures.simulationStatus, tick_seconds: 0.05, ...over });

type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>;
function backend(routes: Record<string, Handler>) {
  h.fetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = String(url).replace("http://t/api/v1", "");
    const key = `${init?.method ?? "GET"} ${path.split("?")[0]}`;
    const fn = routes[key];
    if (!fn) return err(404, "no_route");
    return fn(path, init);
  });
}
const common: Record<string, Handler> = {
  "GET /assets": () => json(fixtures.assetsList),
  "GET /models": () => json(fixtures.modelsList),
  "GET /assets/cooling-01/readings": () => json(fixtures.assetReadings),
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><SimulatePage /></QueryClientProvider>);
}
const startBtn = () => screen.getByRole("button", { name: /start simulation/i });

beforeEach(() => h.fetch.mockReset());
afterEach(() => vi.clearAllMocks());

describe("SimulatePage (live API, mocked HTTP)", () => {
  it("only offers cooling-rule-v1 assets", async () => {
    backend({ ...common, "GET /simulations": () => json(page([])) });
    renderPage();
    const select = await screen.findByRole("combobox");
    expect(Array.from((select as HTMLSelectElement).options).map((o) => o.value)).toEqual(["cooling-01"]);
  });

  it("starts, polls every 2 s to completed, keeps the run available, then resets", { timeout: 15000 }, async () => {
    let polls = 0;
    let started = false;
    backend({
      ...common,
      "GET /simulations": () => json(page(started ? [sim()] : [])),
      "POST /simulations": (_p, init) => {
        expect(JSON.parse(String(init?.body))).toEqual({ scenario: "cooling_anomaly", asset_id: "cooling-01", seed: 42 });
        started = true;
        return json(sim({ samples_emitted: 0 }));
      },
      "GET /simulations/sim-demo-001": () => {
        polls += 1;
        return json(polls < 2 ? sim({ samples_emitted: polls * 10 }) : sim({ status: "completed", samples_emitted: 30, completed_at: "2026-11-07T20:01:00Z" }));
      },
      "POST /simulations/sim-demo-001/reset": () => { started = false; return json(fixtures.simulationReset); },
    });
    renderPage();
    await waitFor(() => expect(startBtn()).toBeEnabled());
    fireEvent.click(startBtn());
    expect(await screen.findByText("Status: running")).toBeInTheDocument();
    expect(startBtn()).toBeDisabled();
    expect(await screen.findByText("Status: completed", {}, { timeout: 8000 })).toBeInTheDocument();
    expect(polls).toBeGreaterThanOrEqual(2);
    expect(await screen.findByRole("img", { name: /Temperature/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reset simulation" })).toBeInTheDocument();
    const readsBefore = h.fetch.mock.calls.filter((c) => String(c[0]).includes("/readings")).length;
    fireEvent.click(screen.getByRole("button", { name: "Reset simulation" }));
    expect(await screen.findByText("Readings deleted")).toBeInTheDocument();
    expect(screen.getAllByText("12").length).toBe(2);
    await waitFor(() => expect(h.fetch.mock.calls.filter((c) => String(c[0]).includes("/readings")).length).toBeGreaterThan(readsBefore));
  });

  it("recovers a running simulation after reload and disables start", async () => {
    backend({ ...common, "GET /simulations": () => json(page([sim()])), "GET /simulations/sim-demo-001": () => json(sim()) });
    renderPage();
    expect(await screen.findByText("Status: running")).toBeInTheDocument();
    expect(startBtn()).toBeDisabled();
    const calls = h.fetch.mock.calls.map((c) => String(c[0]));
    expect(calls).toContain("http://t/api/v1/simulations?asset_id=cooling-01");
  });

  it("on 409 refetches running simulations and shows the existing run", async () => {
    let listCalls = 0;
    backend({
      ...common,
      "GET /simulations": () => { listCalls += 1; return json(page(listCalls > 1 ? [sim()] : [])); },
      "POST /simulations": () => err(409, "SIMULATION_ALREADY_RUNNING"),
      "GET /simulations/sim-demo-001": () => json(sim()),
    });
    renderPage();
    await waitFor(() => expect(startBtn()).toBeEnabled());
    fireEvent.click(startBtn());
    expect(await screen.findByText(/already running/)).toBeInTheDocument();
    expect(await screen.findByText("Status: running")).toBeInTheDocument();
    expect(listCalls).toBeGreaterThanOrEqual(2);
  });

  it("shows recovery failure with request id and keeps start disabled", async () => {
    backend({ ...common, "GET /simulations": () => err(503, "unavailable") });
    renderPage();
    expect(await screen.findByText("Could not check for a running simulation", { selector: "p" })).toBeInTheDocument();
    expect(screen.getByText(/request_id req-503/)).toBeInTheDocument();
    expect(startBtn()).toBeDisabled();
  });

  it("shows fleet conflict with request ID and fleet link without claiming single-asset recovery", async () => {
    backend({ ...common, "GET /simulations": () => json(page([])), "POST /simulations": () => err(409, "FLEET_LIVE_RUNNING") });
    renderPage();
    await waitFor(() => expect(startBtn()).toBeEnabled());
    fireEvent.click(startBtn());
    expect(await screen.findByText("backend says FLEET_LIVE_RUNNING")).toBeInTheDocument();
    expect(screen.getByText(/request_id req-409/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Live fleet" })).toHaveAttribute("href", "/fleet");
    expect(screen.queryByText(/already running for this asset/)).not.toBeInTheDocument();
    expect(h.fetch.mock.calls.filter((c) => String(c[0]).includes('/simulations?')).length).toBe(1);
  });

  it("shows asset load errors without fallback options", async () => {
    backend({ ...common, "GET /assets": () => err(503, "unavailable") });
    renderPage();
    expect(await screen.findByText("Could not load assets")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("shows empty state when no compatible assets exist", async () => {
    backend({ ...common, "GET /assets": () => json(page([fixtures.assetsList.items[1]])) });
    renderPage();
    expect(await screen.findByText(/No assets compatible/)).toBeInTheDocument();
  });

  it("rejects non-integer seeds", async () => {
    backend({ ...common, "GET /simulations": () => json(page([])) });
    renderPage();
    await waitFor(() => expect(startBtn()).toBeEnabled());
    fireEvent.change(screen.getByLabelText(/Seed/), { target: { value: "4.5" } });
    expect(startBtn()).toBeDisabled();
    expect(screen.getByText("Seed must be a whole number of 0 or more.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Seed/), { target: { value: "-1" } });
    expect(startBtn()).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/Seed/), { target: { value: "0" } });
    expect(startBtn()).toBeEnabled();
  });

  it("keeps start disabled while a recovered run is still loading", async () => {
    backend({ ...common, "GET /simulations": () => json(page([sim()])), "GET /simulations/sim-demo-001": () => new Promise<Response>(() => {}) });
    renderPage();
    expect(await screen.findByText("Loading recovered simulation…", { selector: "span" })).toBeInTheDocument();
    expect(startBtn()).toBeDisabled();
  });
});
