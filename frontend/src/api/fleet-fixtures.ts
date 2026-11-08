import type { ClearResponse, FaultRequest, FaultResponse, FleetMap, FleetStatus, LiveStartRequest, LiveStatus, RackDetail, SitesResponse } from './fleet-types';
import type { IncidentDetail } from './types';
import type { Widen } from './fixtures';
import map from './fixtures/contracts/fleet.map.response.json';
import status from './fixtures/contracts/fleet.status.response.json';
import mining from './fixtures/contracts/fleet.status.mining.response.json';
import sites from './fixtures/contracts/fleet.sites.response.json';
import rack from './fixtures/contracts/fleet.rack.response.json';
import live from './fixtures/contracts/fleet.live.response.json';
import clear from './fixtures/contracts/fleet.clear.response.json';
import faults from './fixtures/contracts/fleet.faults.response.json';
import faultRequest from './fixtures/contracts/fleet.faults.request.json';
import startRequest from './fixtures/contracts/fleet.live.start.request.json';
import minerIncident from './fixtures/contracts/incident.miner.response.json';
const checks: [Widen<FleetMap>, Widen<FleetStatus>, Widen<FleetStatus>, Widen<SitesResponse>, Widen<RackDetail>, Widen<LiveStatus>, Widen<ClearResponse>, Widen<FaultResponse>, Widen<LiveStartRequest>, Widen<IncidentDetail>] = [map, status, mining, sites, rack, live, clear, faults, startRequest, minerIncident];
// Public fault request also supports explicit asset_ids instead of a site.
const requestCheck: Widen<Partial<FaultRequest> & { asset_ids?: string[] }> = faultRequest;
void [checks, requestCheck];
export const fleetFixtures = {
  map: map as unknown as FleetMap, status: status as unknown as FleetStatus, mining: mining as unknown as FleetStatus,
  sites: sites as unknown as SitesResponse, rack: rack as unknown as RackDetail, minerIncident: minerIncident as unknown as IncidentDetail,
};
// Mutation responses are compatibility-checked above, never executed in fixture mode.