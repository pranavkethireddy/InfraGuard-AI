import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { IncidentPatch, SimulationRequest } from "./types";

const POLL_MS = 15_000;
/** Simulation status and readings are polled every 2 s while a run is active. */
export const SIM_POLL_MS = 2_000;
export const simulationPollInterval = (status: string | undefined): number | false => (status === "running" ? SIM_POLL_MS : false);

export const assetsQuery = () =>
  queryOptions({ queryKey: ["assets"], queryFn: () => api.listAssets({ limit: 100 }), refetchInterval: POLL_MS });
export const assetQuery = (id: string) => queryOptions({ queryKey: ["assets", id], queryFn: () => api.getAsset(id) });
export const readingsQuery = (id: string, limit = 500) =>
  queryOptions({ queryKey: ["assets", id, "readings", limit], queryFn: () => api.getReadings(id, { limit }), refetchInterval: POLL_MS });
export const incidentsQuery = (status?: "open" | "acknowledged" | "resolved") =>
  queryOptions({ queryKey: ["incidents", { status }], queryFn: () => api.listIncidents({ status, limit: 100 }), refetchInterval: POLL_MS });
export const incidentQuery = (id: string) => queryOptions({ queryKey: ["incident", id], queryFn: () => api.getIncident(id) });
export const modelsQuery = () => queryOptions({ queryKey: ["models"], queryFn: () => api.listModels() });
export const runningSimulationsQuery = (assetId: string) =>
  queryOptions({
    queryKey: ["simulations", "running", assetId],
    queryFn: () => api.listSimulations({ status: "running", asset_id: assetId }),
    retry: false,
  });
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
