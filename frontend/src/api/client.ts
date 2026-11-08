import type {
  Asset, AssetDetail, DetectorModel, ErrorEnvelope, IncidentDetail, IncidentPatch, IncidentStatus,
  IncidentSummary, Paginated, ReadingsPage, Simulation, SimulationRequest, SimulationReset,
} from "./types";
import { fixtures } from "./fixtures";
import { DEFAULT_DATA_MODE } from "./mode-default";
import { fleetFixtures } from './fleet-fixtures';
import { opsFixtures } from './ops-fixtures';
import { gpuFixtures } from './gpu-fixtures';
import type { AutoDispatchResponse, DispatchRequest, DispatchResponse, FloorPlan, LearningCases, LearningMatrix, PagerActionRequest, PagerView, PlanResponse, TechniciansResponse, WhatIfResponse } from './ops-types';
import { pagerFixtures } from './pager-fixtures';
import type { ClearResponse, FaultRequest, FaultResponse, FleetMap, FleetStatus, LiveStartRequest, LiveStatus, RackDetail, ServerDetail, SiteId, SitesResponse } from './fleet-types';

// VITE_* values are bundled into the browser. Never put secrets in them.
export type DataMode = "fixture" | "live";
/** Explicit VITE_DATA_MODE wins; otherwise the build target's default (preview: fixture, frontend/ export: live). */
export function resolveDataMode(raw: string | undefined, fallback: DataMode): DataMode {
  return raw === "live" || raw === "fixture" ? raw : fallback;
}
export const DATA_MODE: DataMode = resolveDataMode(import.meta.env.VITE_DATA_MODE, DEFAULT_DATA_MODE);
export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL || "/api/v1").replace(/\/+$/, '');

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number | null,
    public code: string,
    public requestId: string | null = null,
    public details: unknown = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export const FIXTURE_MUTATION_MESSAGE =
  "Disabled in fixture preview. Set VITE_DATA_MODE=live and run the backend to perform this action.";

export interface ReadingsQuery { start?: string | undefined; end?: string | undefined; limit?: number | undefined }
export interface ListQuery { limit?: number | undefined; offset?: number | undefined; status?: IncidentStatus | undefined }
export interface SimulationListQuery { status?: "running" | undefined; asset_id?: string | undefined }

export interface ApiClient {
  mode: DataMode;
  listAssets(q?: ListQuery): Promise<Paginated<Asset>>;
  getAsset(id: string): Promise<AssetDetail>;
  getReadings(id: string, q?: ReadingsQuery): Promise<ReadingsPage>;
  listIncidents(q?: ListQuery): Promise<Paginated<IncidentSummary>>;
  getIncident(id: string): Promise<IncidentDetail>;
  patchIncident(id: string, body: IncidentPatch): Promise<IncidentDetail>;
  /** POST /incidents/{id}/investigate (no body). May take 10-30 s or longer. */
  investigateIncident(id: string): Promise<IncidentDetail>;
  listSimulations(q: SimulationListQuery): Promise<Paginated<Simulation>>;
  getSimulation(id: string): Promise<Simulation>;
  startSimulation(body: SimulationRequest): Promise<Simulation>;
  resetSimulation(id: string): Promise<SimulationReset>;
  listModels(): Promise<Paginated<DetectorModel>>;
  fleetSites(): Promise<SitesResponse>;
  fleetMap(site: SiteId): Promise<FleetMap>;
  fleetStatus(site: SiteId): Promise<FleetStatus>;
  fleetRack(id: string): Promise<RackDetail>;
  fleetServer(id: string): Promise<ServerDetail>;
  startFleet(body?: LiveStartRequest): Promise<LiveStatus>;
  stopFleet(): Promise<LiveStatus>;
  injectFaults(body: FaultRequest): Promise<FaultResponse>;
  clearFleet(): Promise<ClearResponse>;
  incidentWhatIf(id: string): Promise<WhatIfResponse>;
  opsTechnicians(site: SiteId): Promise<TechniciansResponse>;
  opsFloor(site: SiteId): Promise<FloorPlan>;
  opsPager(id: string): Promise<PagerView>;
  claimPager(id: string): Promise<PagerView>;
  releasePager(id: string): Promise<PagerView>;
  pagerAction(id: string, body: PagerActionRequest): Promise<PagerView>;
  setAutoDispatch(enabled: boolean): Promise<AutoDispatchResponse>;
  opsPlan(site: SiteId): Promise<PlanResponse>;
  dispatch(body: DispatchRequest): Promise<DispatchResponse>;
  learningMatrix(): Promise<LearningMatrix>;
  learningCases(site: SiteId, assetType?: string): Promise<LearningCases>;
}

function qs(params: Record<string, string | number | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

const FRIENDLY: Record<number, string> = {
  404: "The requested item was not found.",
  409: "This conflicts with the current state (for example, a simulation is already running).",
  422: "The request was rejected as invalid.",
  503: "The backend service is temporarily unavailable.",
};

export function createLiveClient(baseUrl = API_BASE_URL, fetchImpl: typeof fetch = (...a) => fetch(...a)): ApiClient {
  async function req<T>(path: string, init?: RequestInit): Promise<T> {
    let res: Response;
    try {
      res = await fetchImpl(`${baseUrl.replace(/\/+$/, '')}${path}`, {
        ...init,
        headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}) },
      });
    } catch (e) {
      throw new ApiError(`Cannot reach the API at ${baseUrl}. ${(e as Error).message}`, null, "network_error");
    }
    if (!res.ok) {
      let env: ErrorEnvelope | null = null;
      try { env = (await res.json()) as ErrorEnvelope; } catch { /* non-JSON body */ }
      const e = env?.error;
      throw new ApiError(
        e?.message || FRIENDLY[res.status] || `Request failed (HTTP ${res.status}).`,
        res.status,
        e?.code || `http_${res.status}`,
        e?.request_id ?? res.headers.get("x-request-id"),
        e?.details ?? null,
      );
    }
    return (await res.json()) as T;
  }
  const enc = encodeURIComponent;
  const json = (method: string, body?: unknown): RequestInit => (body === undefined ? { method } : { method, body: JSON.stringify(body) });
  return {
    mode: "live",
    listAssets: (q = {}) => req(`/assets${qs({ limit: q.limit, offset: q.offset })}`),
    getAsset: (id) => req(`/assets/${enc(id)}`),
    getReadings: (id, q = {}) => req(`/assets/${enc(id)}/readings${qs({ start: q.start, end: q.end, limit: q.limit })}`),
    listIncidents: (q = {}) => req(`/incidents${qs({ limit: q.limit, offset: q.offset, status: q.status })}`),
    getIncident: (id) => req(`/incidents/${enc(id)}`),
    patchIncident: (id, body) => req(`/incidents/${enc(id)}`, json("PATCH", body)),
    investigateIncident: (id) => req(`/incidents/${enc(id)}/investigate`, json("POST")),
    listSimulations: (q) => req(`/simulations${qs({ status: q.status, asset_id: q.asset_id })}`),
    getSimulation: (id) => req(`/simulations/${enc(id)}`),
    startSimulation: (body) => req(`/simulations`, json("POST", body)),
    resetSimulation: (id) => req(`/simulations/${enc(id)}/reset`, json("POST")),
    listModels: () => req(`/models`),
    fleetSites: () => req('/fleet/sites'),
    fleetMap: (site) => req(`/fleet/map${qs({ site, history: 30 })}`),
    fleetStatus: (site) => req(`/fleet/status${qs({ site, history: 30 })}`),
    fleetRack: (id) => req(`/fleet/racks/${enc(id)}?history=30`),
    fleetServer: (id) => req(`/fleet/servers/${enc(id)}?history=30`),
    startFleet: (body) => req('/fleet/live/start', json('POST', body)),
    stopFleet: () => req('/fleet/live/stop', json('POST')),
    injectFaults: (body) => req('/fleet/faults', json('POST', body)),
    clearFleet: () => req('/fleet/clear', json('POST')),
    incidentWhatIf: (id) => req(`/incidents/${enc(id)}/whatif`),
    opsTechnicians: (site) => req(`/ops/technicians${qs({ site })}`),
    opsFloor: (site) => req(`/ops/floor${qs({ site })}`),
    opsPager: (id) => req(`/ops/pager/${enc(id)}`),
    claimPager: (id) => req(`/ops/pager/${enc(id)}/claim`, json('POST')),
    releasePager: (id) => req(`/ops/pager/${enc(id)}/release`, json('POST')),
    pagerAction: (id, body) => req(`/ops/pager/${enc(id)}/action`, json('POST', body)),
    setAutoDispatch: (enabled) => req('/ops/auto-dispatch', json('POST', { enabled })),
    opsPlan: (site) => req(`/ops/plan${qs({ site })}`),
    dispatch: (body) => req('/ops/dispatch', json('POST', body)),
    learningMatrix: () => req('/learning/matrix'),
    learningCases: (site, asset_type) => req(`/learning/cases${qs({ site, asset_type })}`),
  };
}

const later = <T,>(v: T) => new Promise<T>((r) => setTimeout(() => r(structuredClone(v)), 80));
const notFound = (what: string) => new ApiError(`${what} was not found.`, 404, "not_found");
const disabled = () => Promise.reject(new ApiError(FIXTURE_MUTATION_MESSAGE, null, "fixture_mode"));

/**
 * Serves the approved contract fixtures verbatim. Only resources that have a fixture
 * are returned; anything else is a 404, never synthesised data.
 */
export function createFixtureClient(): ApiClient {
  const f = fixtures;
  return {
    mode: "fixture",
    listAssets: () => later(f.assetsList),
    getAsset: (id) => (id === f.assetDetail.asset_id ? later(f.assetDetail) : Promise.reject(notFound(`Asset detail for "${id}" (no fixture)`))),
    getReadings: (id) => (id === f.assetReadings.asset_id ? later(f.assetReadings) : Promise.reject(notFound(`Readings for "${id}" (no fixture)`))),
    listIncidents: (q = {}) =>
      later({ ...f.incidentsList, items: f.incidentsList.items.filter((i) => !q.status || i.status === q.status) }),
    getIncident: (id) => (id === f.incidentDetail.incident_id ? later(f.incidentDetail) : id === fleetFixtures.minerIncident.incident_id ? later(fleetFixtures.minerIncident) : Promise.reject(notFound(`Incident "${id}"`))),
    patchIncident: disabled,
    investigateIncident: disabled,
    // No running simulation is reported in fixture mode: no fake live progress.
    listSimulations: () => later<Paginated<Simulation>>({ items: [], total: 0, limit: 50, offset: 0 }),
    getSimulation: (id) => (id === f.simulationStatus.simulation_id ? later(f.simulationStatus) : Promise.reject(notFound(`Simulation "${id}"`))),
    startSimulation: disabled,
    resetSimulation: disabled,
    listModels: () => later(f.modelsList),
    fleetSites: () => later(fleetFixtures.sites),
    fleetMap: (site) => site === fleetFixtures.map.site_id ? later(fleetFixtures.map) : Promise.reject(notFound(`Map for ${site} (no approved fixture)`)),
    fleetStatus: (site) => later(site === 'mining' ? fleetFixtures.mining : fleetFixtures.status),
    fleetRack: (id) => id === fleetFixtures.rack.rack_id ? later(fleetFixtures.rack) : Promise.reject(notFound(`Rack ${id} (no approved fixture)`)),
    fleetServer: (id) => id === gpuFixtures.server.machine.asset_id ? later(gpuFixtures.server) : id === gpuFixtures.crashed.machine.asset_id ? later(gpuFixtures.crashed) : Promise.reject(notFound(`Server ${id} (no approved fixture)`)),
    startFleet: disabled, stopFleet: disabled, injectFaults: disabled, clearFleet: disabled,
    incidentWhatIf: (id) => id === opsFixtures.whatif.incident_id ? later(opsFixtures.whatif) : id === gpuFixtures.whatif.incident_id ? later(gpuFixtures.whatif) : Promise.reject(notFound(`What-if for ${id} (no approved fixture)`)),
    opsTechnicians: (site) => later({ ...opsFixtures.technicians, technicians: opsFixtures.technicians.technicians.filter((t) => t.site_id === site), work_orders: opsFixtures.technicians.work_orders.filter((w) => w.site_id === site) }),
    opsFloor: (site) => site === pagerFixtures.floor.site_id ? later(pagerFixtures.floor) : Promise.reject(notFound(`Floor for ${site} (no approved fixture)`)),
    opsPager: (id) => id === pagerFixtures.paged.technician.technician_id ? later(pagerFixtures.paged) : Promise.reject(notFound(`Pager ${id} (no approved fixture)`)),
    claimPager: disabled, releasePager: disabled, pagerAction: disabled, setAutoDispatch: disabled,
    opsPlan: (site) => site === opsFixtures.plan.site_id ? later(opsFixtures.plan) : Promise.reject(notFound(`Plan for ${site} (no approved fixture)`)),
    dispatch: disabled,
    learningMatrix: () => later(opsFixtures.matrix),
    learningCases: (site, type) => { const items = opsFixtures.cases.items.filter((c) => c.site_id === site && (!type || c.asset_type === type)); return later({ items, total: items.length }); },
  };
}

// Explicit mode selection. Live-mode errors surface to the UI; there is no fallback to fixtures.
export const api: ApiClient = DATA_MODE === "live" ? createLiveClient() : createFixtureClient();
