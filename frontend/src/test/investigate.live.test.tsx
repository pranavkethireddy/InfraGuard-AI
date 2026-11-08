import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock("@/api/client", async (orig) => {
  const m = await orig<typeof import("@/api/client")>();
  return { ...m, DATA_MODE: "live", api: m.createLiveClient("http://t/api/v1", (...a) => h.fetch(...a)) };
});

import { IncidentDetailPage } from "@/pages/IncidentDetailPage";
import { fixtures } from "@/api/fixtures";
// Test-only: approved agent response contract; never served in fixture mode.
import investigatedJson from "@/api/fixtures/contracts/incident.investigate.response.json";
import type { IncidentDetail } from "@/api/types";
import type { Widen } from "@/api/fixtures";
const _check: Widen<IncidentDetail> = investigatedJson;
void _check;
const investigated = investigatedJson as unknown as IncidentDetail;

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status, headers: { "Content-Type": "application/json" } });
let resolveInvestigate: ((r: Response) => void) | null = null;
let investigateCalls = 0;

function backend(investigate: () => Promise<Response>) {
  h.fetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = String(url).replace("http://t/api/v1", "").split("?")[0];
    const key = `${init?.method ?? "GET"} ${path}`;
    if (key === "GET /incidents/inc-demo-001") return json(fixtures.incidentDetail);
    if (key === "GET /assets/cooling-01/readings") return json(fixtures.assetReadings);
    if (key === "GET /models") return json(fixtures.modelsList);
    if (key === "POST /incidents/inc-demo-001/investigate") { investigateCalls += 1; expect(init?.body).toBeUndefined(); return investigate(); }
    return json({ error: { code: "no_route", message: "no", details: null, request_id: null } }, 404);
  });
}
function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><IncidentDetailPage id="inc-demo-001" /></QueryClientProvider>);
}
const btn = () => screen.getByRole("button", { name: /Investigat|Retry investigation/ });

beforeEach(() => { h.fetch.mockReset(); investigateCalls = 0; resolveInvestigate = null; });

describe("Incident investigation (live, mocked HTTP)", () => {
  it("shows pending state, blocks duplicates, keeps evidence, then shows agent result", async () => {
    backend(() => new Promise<Response>((r) => { resolveInvestigate = r; }));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Investigate" }));
    await waitFor(() => expect(btn()).toHaveAttribute("aria-busy", "true"));
    expect(btn()).toBeDisabled();
    fireEvent.click(btn());
    expect(investigateCalls).toBe(1);
    expect(screen.getByText("Rule evidence")).toBeInTheDocument();
    resolveInvestigate!(json(investigated));
    expect(await screen.findByText(investigated.explanation!)).toBeInTheDocument();
    expect(screen.getByText(/AI agent investigation — human review required/)).toBeInTheDocument();
    expect(screen.getByText(investigated.agent_steps![0]!.tool)).toBeInTheDocument();
    expect(screen.getByText("mr-0042")).toBeInTheDocument();
    expect(btn()).toHaveAttribute("aria-busy", "false");
  });

  it("shows request ID on failure, preserves evidence, and allows retry", async () => {
    backend(async () => json({ error: { code: "agent_unavailable", message: "Agent unavailable", details: null, request_id: "req-inv-1" } }, 503));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Investigate" }));
    expect(await screen.findByText(/request_id req-inv-1/)).toBeInTheDocument();
    expect(screen.getByText("Rule evidence")).toBeInTheDocument();
    expect(screen.getByText(fixtures.incidentDetail.explanation!)).toBeInTheDocument();
    const retry = screen.getByRole("button", { name: "Retry investigation" });
    expect(retry).toBeEnabled();
    fireEvent.click(retry);
    await waitFor(() => expect(investigateCalls).toBe(2));
  });
});
