import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import { listAllAssets } from './all-assets';
import type { IncidentDetail, IncidentPatch, Simulation, SimulationRequest } from "./types";

const POLL_MS = 15_000;
/** Simulation status and readings are polled every 2 s while a run is active. */
export const SIM_POLL_MS = 2_000;
export const simulationPollInterval = (status: string | undefined): number | false => (status === "running" ? SIM_POLL_MS : false);

export const assetsQuery = (limit = 100, offset = 0) =>
  queryOptions({ queryKey: ["assets", { limit, offset }], queryFn: () => api.listAssets({ limit, offset }), refetchInterval: POLL_MS });
export const assetQuery = (id: string) => queryOptions({ queryKey: ["assets", id], queryFn: () => api.getAsset(id) });
export const simulatorAssetsQuery = () => queryOptions({ queryKey: ['assets', 'simulator-all'], queryFn: () => listAllAssets(api), refetchInterval: POLL_MS });
export const readingsQuery = (id: string, limit = 500) =>
  queryOptions({ queryKey: ["assets", id, "readings", limit], queryFn: () => api.getReadings(id, { limit }), refetchInterval: POLL_MS });
export const incidentsQuery = (status?: "open" | "acknowledged" | "resolved") =>
  queryOptions({ queryKey: ["incidents", { status }], queryFn: () => api.listIncidents({ status, limit: 100 }), refetchInterval: api.mode === 'live' ? 1_000 : POLL_MS });
export const investigationPollInterval = (status: string | null | undefined): number | false => status === 'queued' || status === 'running' ? 1_000 : false;
export const incidentPollInterval = (incident: Pick<IncidentDetail, 'status' | 'work_order_id' | 'investigation_status'> | undefined): number | false =>
  incident && incident.status !== 'resolved' ? 1_000 : investigationPollInterval(incident?.investigation_status);
export const incidentQuery = (id: string) => queryOptions({ queryKey: ["incident", id], queryFn: () => api.getIncident(id), refetchInterval: (q) => incidentPollInterval(q.state.data) });
export const modelsQuery = () => queryOptions({ queryKey: ["models"], queryFn: () => api.listModels() });
/** Recovery: all runs for an asset in backend order; the page picks the active one (see pickRecoverableSimulation). */
export const assetSimulationsQuery = (assetId: string) =>
  queryOptions({
    queryKey: ["simulations", "asset", assetId],
    queryFn: () => api.listSimulations({ asset_id: assetId }),
    retry: false,
  });
/** Prefer a running run, otherwise the first (newest, per backend ordering) completed run. Reset runs are never active. */
export function pickRecoverableSimulation(items: Simulation[]): Simulation | null {
  return items.find((s) => s.status === "running") ?? items.find((s) => s.status === "completed") ?? null;
}
export const simulationQuery = (id: string) =>
  queryOptions({
    queryKey: ["simulation", id],
    queryFn: () => api.getSimulation(id),
    refetchInterval: (q) => simulationPollInterval(q.state.data?.status),
  });

export function useInvalidateAll() {
  const qc = useQueryClient();
  return () => {
    for (const key of ["assets", "incidents", "incident", "simulations", "simulation"]) qc.invalidateQueries({ queryKey: [key] });
  };
}

export function usePatchIncident(id: string) {
  const invalidate = useInvalidateAll();
  return useMutation({ mutationFn: (body: IncidentPatch) => api.patchIncident(id, body), onSuccess: invalidate });
}
export function useStartSimulation() {
  const invalidate = useInvalidateAll();
  return useMutation({ mutationFn: (body: SimulationRequest) => api.startSimulation(body), onSuccess: invalidate });
}
export function useResetSimulation() {
  const invalidate = useInvalidateAll();
  return useMutation({ mutationFn: (id: string) => api.resetSimulation(id), onSuccess: invalidate });
}

/** Agent investigation: on success the returned detail replaces the cached incident. */
export function useInvestigateIncident(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.investigateIncident(id),
    onSuccess: (detail) => {
      qc.setQueryData(incidentQuery(id).queryKey, detail);
      void qc.invalidateQueries({ queryKey: ["incidents"] });
    },
  });
}
