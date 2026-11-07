import { describe, expect, it, vi } from "vitest";
import { ApiError, createFixtureClient, createLiveClient } from "./client";

const envelope = (status: number, code: string) =>
  new Response(JSON.stringify({ error: { code, message: `msg ${code}`, details: null, request_id: "req-123" } }), {
    status, headers: { "Content-Type": "application/json" },
  });

describe("live api client", () => {
  it("parses the error envelope including request ID on 409", async () => {
    const c = createLiveClient("http://x/api/v1", vi.fn().mockResolvedValue(envelope(409, "simulation_running")));
    const err = await c.startSimulation({ scenario: "normal", asset_id: "cooling-01", seed: 42 }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(409);
    expect(err.code).toBe("simulation_running");
    expect(err.requestId).toBe("req-123");
  });

  it.each([404, 422, 503])("throws a typed error for HTTP %i, never fixture data", async (s) => {
    const c = createLiveClient("http://x/api/v1", vi.fn().mockResolvedValue(envelope(s, "e")));
    await expect(c.listAssets()).rejects.toMatchObject({ status: s });
  });

  it("throws network_error when unreachable", async () => {
    const c = createLiveClient("http://x/api/v1", vi.fn().mockRejectedValue(new TypeError("fail")));
    await expect(c.listModels()).rejects.toMatchObject({ code: "network_error" });
  });

  it("builds the readings query string", async () => {
    const f = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    await createLiveClient("http://x/api/v1", f).getReadings("cooling-01", { start: "a", limit: 5 });
    expect(f.mock.calls[0]?.[0]).toBe("http://x/api/v1/assets/cooling-01/readings?start=a&limit=5");
  });
});

describe("fixture client", () => {
  it("serves contract fixture values unchanged", async () => {
    const c = createFixtureClient();
    const i = await c.getIncident("inc-demo-001");
    expect(i.impact?.estimated_total_impact).toBe(51500);
    expect(i.priority_index).toBe(0.86);
    expect(i.latest_prediction?.score_kind).toBe("heuristic");
    const r = await c.getReadings("cooling-01");
    expect(r.items.map((x) => x.values["temperature_c"])).toEqual([33.1, 35]);
  });
  it("refuses mutations", async () => {
    await expect(createFixtureClient().patchIncident("inc-demo-001", { status: "resolved", note: null })).rejects.toMatchObject({ code: "fixture_mode" });
    await expect(createFixtureClient().startSimulation({ scenario: "normal", asset_id: "cooling-01", seed: 1 })).rejects.toMatchObject({ code: "fixture_mode" });
  });
  it("returns 404 rather than inventing data for resources without a fixture", async () => {
    await expect(createFixtureClient().getAsset("mill-01")).rejects.toMatchObject({ status: 404 });
  });
});
