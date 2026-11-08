import { queryOptions } from '@tanstack/react-query';
import { api } from './client';
import type { SiteId } from './fleet-types';
export const FLEET_POLL_MS = 1_000;
export const fleetSitesQuery = () => queryOptions({ queryKey: ['fleet', 'sites'], queryFn: () => api.fleetSites(), refetchInterval: FLEET_POLL_MS });
export const fleetMapQuery = (site: SiteId) => queryOptions({ queryKey: ['fleet', site, 'map', 30], queryFn: () => api.fleetMap(site), refetchInterval: FLEET_POLL_MS });
export const fleetStatusQuery = (site: SiteId) => queryOptions({ queryKey: ['fleet', site, 'status', 30], queryFn: () => api.fleetStatus(site), refetchInterval: FLEET_POLL_MS });
export const fleetRackQuery = (site: SiteId, id: string) => queryOptions({ queryKey: ['fleet', site, 'rack', id, 30], queryFn: () => api.fleetRack(id), refetchInterval: FLEET_POLL_MS });