import type { FailureMode } from './types';

export type ComponentKind = 'gpu' | 'cpu' | 'dimm' | 'fan' | 'psu' | 'nic' | 'nvme' | 'bmc';
export type ComponentStatus = 'ok' | 'warning' | 'failed' | 'offline';
export interface ServerComponent {
  component_id: string; kind: ComponentKind; name: string; status: ComponentStatus;
  metrics: Record<string, number>; note: string | null;
}
export interface ServerComponents {
  server_id: string; observed_at: string | null; components: ServerComponent[];
}
export interface ComponentHistory {
  observed_at: string; status: ComponentStatus; metrics: Record<string, number>;
}
export interface ComponentDetail {
  server_id: string; component: ServerComponent; history: ComponentHistory[]; failure_mode: FailureMode | null;
}

export function metricUnit(metric: string): string | null {
  const units: Record<string, string> = { temp_c: '°C', clock_pct: '%', util_pct: '%', wear_pct: '%', ecc_errors: 'count', crc_errors: 'count', rpm: 'rpm', watts: 'W', link_up: 'binary 0/1', ok: 'binary 0/1' };
  return units[metric] ?? null;
}
export const serverPath = (id: string) => `/fleet/servers/${encodeURIComponent(id)}`;
export const componentPath = (id: string, cid: string) => `${serverPath(id)}/components/${encodeURIComponent(cid)}`;
export const rackPath = (id: string) => `/fleet/racks/${encodeURIComponent(id)}`;