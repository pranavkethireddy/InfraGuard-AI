import type {
  Asset, AssetDetail, DetectorModel, ErrorEnvelope, IncidentDetail, IncidentPatch, IncidentStatus,
  IncidentSummary, Paginated, ReadingsPage, Simulation, SimulationRequest, SimulationReset,
} from "./types";
import { fixtures } from "./fixtures";

// VITE_* values are bundled into the browser. Never put secrets in them.
export type DataMode = "fixture" | "live";
export const DATA_MODE: DataMode = import.meta.env.VITE_DATA_MODE === "live" ? "live" : "fixture";
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

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
  listSimulations(q: SimulationListQuery): Promise<Paginated<Simulation>>;
  getSimulation(id: string): Promise<Simulation>;
  startSimulation(body: SimulationRequest): Promise<Simulation>;
  resetSimulation(id: string): Promise<SimulationReset>;
  listModels(): Promise<Paginated<DetectorModel>>;
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
      res = await fetchImpl(`${baseUrl}${path}`, {
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
    listSimulations: (q) => req(`/simulations${qs({ status: q.status, asset_id: q.asset_id })}`),
    getSimulation: (id) => req(`/simulations/${enc(id)}`),
    startSimulation: (body) => req(`/simulations`, json("POST", body)),
    resetSimulation: (id) => req(`/simulations/${enc(id)}/reset`, json("POST")),
    listModels: () => req(`/models`),
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
    getIncident: (id) => (id === f.incidentDetail.incident_id ? later(f.incidentDetail) : Promise.reject(notFound(`Incident "${id}"`))),
    patchIncident: disabled,
    // No running simulation is reported in fixture mode: no fake live progress.
    listSimulations: () => later<Paginated<Simulation>>({ items: [], total: 0, limit: 50, offset: 0 }),
    getSimulation: (id) => (id === f.simulationStatus.simulation_id ? later(f.simulationStatus) : Promise.reject(notFound(`Simulation "${id}"`))),
    startSimulation: disabled,
    resetSimulation: disabled,
    listModels: () => later(f.modelsList),
  };
}

// Explicit mode selection. Live-mode errors surface to the UI; there is no fallback to fixtures.
export const api: ApiClient = DATA_MODE === "live" ? createLiveClient() : createFixtureClient();
