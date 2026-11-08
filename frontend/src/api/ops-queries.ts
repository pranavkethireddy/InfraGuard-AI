import { queryOptions, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type { SiteId } from './fleet-types';
import type { DispatchRequest } from './ops-types';
export const OPS_POLL_MS = 1000;
export const whatIfQuery = (id: string) => queryOptions({ queryKey: ['whatif', id], queryFn: () => api.incidentWhatIf(id), refetchInterval: OPS_POLL_MS });
export const techniciansQuery = (site: SiteId) => queryOptions({ queryKey: ['ops', site, 'technicians'], queryFn: () => api.opsTechnicians(site), refetchInterval: OPS_POLL_MS });
export const planQuery = (site: SiteId) => queryOptions({ queryKey: ['ops', site, 'plan'], queryFn: () => api.opsPlan(site), refetchInterval: OPS_POLL_MS });
export const learningMatrixQuery = () => queryOptions({ queryKey: ['learning', 'matrix'], queryFn: () => api.learningMatrix(), refetchInterval: OPS_POLL_MS });
export const learningCasesQuery = (site: SiteId, type?: string) => queryOptions({ queryKey: ['learning', site, 'cases', type], queryFn: () => api.learningCases(site, type), refetchInterval: OPS_POLL_MS });
export function useDispatch() {
  const qc = useQueryClient();
  const refresh = () => { for (const key of ['incident', 'incidents', 'assets', 'fleet', 'whatif', 'ops', 'learning']) void qc.invalidateQueries({ queryKey: [key] }); };
  return useMutation({ mutationKey: ['ops', 'dispatch'], mutationFn: (body: DispatchRequest) => api.dispatch(body), onSuccess: refresh, onError: refresh, retry: false });
}