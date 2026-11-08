import { queryOptions } from '@tanstack/react-query';
import { api, ApiError } from './client';
import type { SiteId } from './fleet-types';
export const FLEET_POLL_MS = 1_000;
export const floorQuery = (site: SiteId) => queryOptions({ queryKey: ['ops', site, 'floor'], queryFn: async () => {
  const floor = await api.opsFloor(site);
  if (floor.site_id !== site || !Number.isFinite(floor.width) || !Number.isFinite(floor.depth) || !Array.isArray(floor.halls) || floor.halls.some((h) => !h.door || !Number.isFinite(h.x) || !Number.isFinite(h.y))) throw new ApiError('Invalid floor response.', null, 'invalid_response');
  return floor;
}, retry: false });
export const fleetChaosQuery = () => queryOptions({ queryKey: ['fleet', 'chaos'], queryFn: async () => {
  const state = await api.fleetChaos();
  if (typeof state?.enabled !== 'boolean' || !Array.isArray(state.protected_technicians) || !Array.isArray(state.active_faults)) throw new ApiError('Invalid chaos status response.', null, 'invalid_response');
  return state;
}, enabled: api.mode === 'live', refetchInterval: api.mode === 'live' ? FLEET_POLL_MS : false, retry: false });
export const fleetSitesQuery = () => queryOptions({ queryKey: ['fleet', 'sites'], queryFn: () => api.fleetSites(), refetchInterval: FLEET_POLL_MS });
export const fleetMapQuery = (site: SiteId) => queryOptions({ queryKey: ['fleet', site, 'map', 30], queryFn: () => api.fleetMap(site), refetchInterval: FLEET_POLL_MS });
export const fleetStatusQuery = (site: SiteId) => queryOptions({ queryKey: ['fleet', site, 'status', 30], queryFn: () => api.fleetStatus(site), refetchInterval: FLEET_POLL_MS });
export const fleetRackQuery = (site: SiteId, id: string) => queryOptions({ queryKey: ['fleet', site, 'rack', id, 30], queryFn: () => api.fleetRack(id), refetchInterval: FLEET_POLL_MS });