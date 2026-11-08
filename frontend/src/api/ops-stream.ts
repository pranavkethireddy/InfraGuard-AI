import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { API_BASE_URL, DATA_MODE, api } from './client';
import type { SiteId } from './fleet-types';
import type { PagerView, TechniciansResponse } from './ops-types';

export type StreamState = 'connecting' | 'live' | 'reconnecting' | 'error' | 'stale' | 'fixture';
export const pagerKey = (id: string) => ['ops', 'pager', id] as const;
export const crewKey = (site: SiteId) => ['ops', site, 'technicians'] as const;
export function opsStreamUrl(params: { site?: SiteId; technician_id?: string }, base = API_BASE_URL) {
  return `${base.replace(/\/$/, '')}/ops/stream?${new URLSearchParams(params).toString()}`;
}
export function isPagerView(value: unknown): value is PagerView {
  if (!value || typeof value !== 'object') return false;
  const p = value as Partial<PagerView>;
  return Number.isSafeInteger(p.version) && !!p.technician && typeof p.technician.technician_id === 'string' && typeof p.demo_time === 'string' && Array.isArray(p.queue) && (p.job === null || (!!p.job && !!p.job.work_order && typeof p.job.work_order.work_order_id === 'string' && Array.isArray(p.job.steps) && Array.isArray(p.job.actions) && p.job.actions.every((a) => ['accept', 'decline', 'done'].includes(a))));
}
export function isCrew(value: unknown): value is TechniciansResponse {
  if (!value || typeof value !== 'object') return false;
  const p = value as Partial<TechniciansResponse>;
  return typeof p.demo_time === 'string' && Array.isArray(p.technicians) && Array.isArray(p.work_orders) && p.technicians.every((t) => typeof t.technician_id === 'string');
}
export function newerPager(current: PagerView | undefined, incoming: PagerView): PagerView {
  return current && current.version > incoming.version ? current : incoming;
}
function useOpsStream<T>({ identity, event, params, accept, write, enabled }: {
  identity: string; event: string; params: { site?: SiteId; technician_id?: string }; accept: (v: unknown) => v is T;
  write: (v: T) => void; enabled: boolean;
}) {
  const [state, setState] = useState<StreamState>(DATA_MODE === 'fixture' ? 'fixture' : 'connecting');
  const [lastEventAt, setLastEventAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const writeRef = useRef(write); writeRef.current = write;
  const acceptRef = useRef(accept); acceptRef.current = accept;
  const site = params.site; const technicianId = params.technician_id;
  useEffect(() => {
    setLastEventAt(null); setError(null);
    if (DATA_MODE === 'fixture') { setState('fixture'); return; }
    if (!enabled) return;
    setState('connecting');
    let alive = true; let last = 0;
    let source: EventSource;
    try { source = new EventSource(opsStreamUrl({ ...(site ? { site } : {}), ...(technicianId ? { technician_id: technicianId } : {}) })); }
    catch { setState('error'); setError('Cannot open event stream. Last good data retained.'); return; }
    const open = () => { if (alive) { setState('live'); setError(null); } };
    const fail = () => { if (alive) { setState(source.readyState === 2 ? 'error' : 'reconnecting'); setError('Stream disconnected. Last good data retained.'); } };
    const message = (raw: Event) => {
      if (!alive) return;
      try {
        const value: unknown = JSON.parse((raw as MessageEvent<string>).data);
        if (!acceptRef.current(value)) throw new Error('Invalid event');
        writeRef.current(value); last = Date.now(); setLastEventAt(last); setState('live'); setError(null);
      } catch { setState('error'); setError('Malformed stream event. Last good data retained.'); }
    };
    source.addEventListener('open', open); source.addEventListener('error', fail); source.addEventListener(event, message);
    const timer = setInterval(() => { if (alive && last && source.readyState !== 1 && Date.now() - last > 10000) setState('stale'); }, 1000);
    return () => { alive = false; clearInterval(timer); source.removeEventListener('open', open); source.removeEventListener('error', fail); source.removeEventListener(event, message); source.close(); };
  }, [identity, event, site, technicianId, enabled]);
  return { state, lastEventAt, error };
}
export function useCrewStream(site: SiteId) {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: crewKey(site), queryFn: async () => {
    const before = qc.getQueryData<TechniciansResponse>(crewKey(site));
    const value = await api.opsTechnicians(site);
    const current = qc.getQueryData<TechniciansResponse>(crewKey(site));
    return current && current !== before ? current : value;
  }, refetchInterval: false });
  const stream = useOpsStream<TechniciansResponse>({ identity: site, params: { site }, event: 'crew', accept: (v): v is TechniciansResponse => isCrew(v) && v.technicians.every((t) => t.site_id === site) && v.work_orders.every((w) => w.site_id === site), enabled: true, write: (value) => qc.setQueryData(crewKey(site), value) });
  return { ...query, stream };
}
export function usePagerStream(id: string) {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: pagerKey(id), queryFn: async () => {
    const value = await api.opsPager(id);
    if (!isPagerView(value) || value.technician.technician_id !== id) throw new Error('Invalid pager response');
    return newerPager(qc.getQueryData<PagerView>(pagerKey(id)), value);
  }, structuralSharing: (old, next) => newerPager(old as PagerView | undefined, next as PagerView), refetchInterval: false });
  const stream = useOpsStream<PagerView>({ identity: id, params: { technician_id: id }, event: 'pager', accept: isPagerView, enabled: true, write: (value) => {
    if (value.technician.technician_id === id) qc.setQueryData<PagerView>(pagerKey(id), (old) => newerPager(old, value));
  } });
  return { ...query, stream };
}