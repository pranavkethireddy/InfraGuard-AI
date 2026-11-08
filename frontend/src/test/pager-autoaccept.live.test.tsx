import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const h = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('@/api/client', async (orig) => { const m = await orig<typeof import('@/api/client')>(); return { ...m, DATA_MODE: 'live', api: m.createLiveClient('/api/v1', (...a) => h.fetch(...a)) }; });
import { PagerPage } from '@/pages/PagerPage';
import { SiteFloor } from '@/components/SiteFloor';
import { IncidentDetailPage } from '@/pages/IncidentDetailPage';
import { pagerFixtures } from '@/api/pager-fixtures';
import { fixtures } from '@/api/fixtures';
import { pagerKey } from '@/api/ops-stream';
import type { PagerView, WorkStatus } from '@/api/ops-types';
const base = pagerFixtures.paged;
function snapshot(status: WorkStatus, version = 10, actions: ('accept' | 'decline' | 'done')[] = []): PagerView {
  if (!base.job) throw new Error('Missing approved job');
  const order = { ...base.job.work_order, status, incident_id: null };
  return { ...base, version, technician: { ...base.technician, current_work_order: order }, job: { ...base.job, incident_id: null, work_order: order, actions } };
}
class Source {
  static all: Source[] = []; readyState = 1;
  listeners = new Map<string, (e: Event) => void>();
  constructor() { Source.all.push(this); }
  addEventListener(k: string, f: (e: Event) => void) { this.listeners.set(k, f); }
  removeEventListener(k: string) { this.listeners.delete(k); } close() {}
  emit(value: PagerView) { this.listeners.get('pager')?.(new MessageEvent('pager', { data: JSON.stringify(value) })); }
}
const json = (v: unknown) => new Response(JSON.stringify(v), { status: 200 });
const posts = () => h.fetch.mock.calls.filter(([, i]) => i?.method === 'POST');
function mount(node = <PagerPage onTechnicianChange={vi.fn()} />) { const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } }); return { qc, ...render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>) }; }
beforeEach(() => { Source.all = []; vi.stubGlobal('EventSource', Source); h.fetch.mockReset(); h.fetch.mockImplementation(async () => json(snapshot('traveling'))); });
afterEach(() => vi.unstubAllGlobals());
it('never exposes legacy accept/decline or auto-accepts on mount/rerender/stream', async () => {
  h.fetch.mockImplementation(async () => json(base)); const view = mount();
  await screen.findByRole('region', { name: 'Current job' });
  expect(screen.queryByRole('button', { name: 'Accept job' })).not.toBeInTheDocument(); expect(screen.queryByRole('button', { name: 'Decline job' })).not.toBeInTheDocument();
  view.rerender(<QueryClientProvider client={view.qc}><PagerPage onTechnicianChange={vi.fn()} /></QueryClientProvider>);
  act(() => Source.all[0]?.emit(snapshot('in_progress', 20))); expect(posts()).toHaveLength(0);
});
it.each(['traveling', 'in_progress', 'awaiting_confirmation', 'done'] as const)('does not infer Done permission from %s or progress', async (status) => {
  const data = snapshot(status); if (data.job) data.job.work_order.progress = 1;
  h.fetch.mockImplementation(async () => json(data)); mount(); await screen.findByRole('region', { name: 'Current job' });
  expect(screen.queryByRole('button', { name: /^Done$/ })).not.toBeInTheDocument(); expect(posts()).toHaveLength(0);
});
it('sends only explicitly returned Done and locks duplicates until backend completion', async () => {
  let finish: ((r: Response) => void) | undefined;
  h.fetch.mockImplementation(async (_u: string, i?: RequestInit) => i?.method === 'POST' ? new Promise<Response>((r) => { finish = r; }) : json(snapshot('awaiting_confirmation', 10, ['done'])));
  mount(); const done = await screen.findByRole('button', { name: /^Done$/ }); fireEvent.click(done); fireEvent.click(done);
  await waitFor(() => expect(posts()).toHaveLength(1)); expect(JSON.parse(posts()[0]?.[1].body)).toEqual({ action: 'done', work_order_id: base.job?.work_order.work_order_id }); expect(done).toBeDisabled();
  await act(async () => finish?.(json(snapshot('done', 11)))); await waitFor(() => expect(screen.queryByRole('button', { name: /^Done$/ })).not.toBeInTheDocument());
});
it('retains controlled state when chaos ignores release and trusts newer response rather than optimistic unlock', async () => {
  const data = snapshot('traveling'); data.technician.device_controlled = true;
  h.fetch.mockImplementation(async () => json({ ...data, version: 11 })); const { qc } = mount();
  fireEvent.click(await screen.findByRole('button', { name: 'Release control' })); await waitFor(() => expect(posts()).toHaveLength(1));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Release control' })).toBeEnabled()); expect(screen.queryByRole('button', { name: 'Take control' })).not.toBeInTheDocument(); expect(qc.getQueryData<PagerView>(pagerKey('tech-03'))?.technician.device_controlled).toBe(true);
});
it('trusts newer preemption, paused displaced queue and later resumed job while rejecting stale replacements', async () => {
  const low = snapshot('in_progress', 10); const { qc } = mount();
  act(() => qc.setQueryData(pagerKey('tech-03'), low)); await screen.findByRole('region', { name: 'Current job' });
  if (!low.job) throw new Error('Missing job');
  const paused = { ...low.job.work_order, status: 'paused' as const, title: 'Paused lower-risk repair' };
  const highOrder = { ...paused, work_order_id: 'returned-high', title: 'Higher-risk repair', status: 'traveling' as const, displaced_work_order_id: paused.work_order_id };
  const path = [{ x: 2, y: 13, hall_id: null }, { x: 40, y: 3, hall_id: 'plant' }, { x: 22, y: 13, hall_id: null }, { x: 24, y: 8, hall_id: 'hall-b' }];
  const high: PagerView = { ...low, version: 20, technician: { ...low.technician, current_work_order: highOrder, queued_work_order_ids: [paused.work_order_id], path }, job: { ...low.job, work_order: highOrder, asset_name: 'Returned urgent asset', why_you: 'Exact backend reason: cabinet first.' }, queue: [paused] };
  act(() => Source.all[0]?.emit(high)); await screen.findByText('Returned urgent asset'); expect(screen.getByText('Exact backend reason: cabinet first.')).toBeInTheDocument(); expect(screen.getByRole('region', { name: 'Queued jobs' })).toHaveTextContent('paused');
  act(() => Source.all[0]?.emit({ ...low, version: 19 })); expect(qc.getQueryData<PagerView>(pagerKey('tech-03'))?.job?.work_order.work_order_id).toBe('returned-high'); expect(qc.getQueryData<PagerView>(pagerKey('tech-03'))?.technician.path).toEqual(path);
  const resumed = { ...low, version: 21 }; act(() => Source.all[0]?.emit(resumed)); await waitFor(() => expect(qc.getQueryData<PagerView>(pagerKey('tech-03'))?.job?.work_order.work_order_id).toBe(paused.work_order_id)); expect(posts()).toHaveLength(0);
});
it('retains every returned cabinet detour waypoint in the floor drawing without shortening', () => {
  const path = [{ x: 2, y: 13, hall_id: null }, { x: 40, y: 3, hall_id: 'plant' }, { x: 22, y: 13, hall_id: null }, { x: 24, y: 8, hall_id: 'hall-b' }];
  render(<SiteFloor floor={pagerFixtures.floor} halls={[]} technicians={[{ ...base.technician, path }]} selected={null} onSelect={vi.fn()} />);
  expect(document.querySelector('[data-technician-path="tech-03"]')).toHaveAttribute('points', '2,13 40,3 22,13 24,8');
});
it('applies approved autoaccepted -> preempted snapshots, exact dispatch displacement and backend why_you', async () => {
  const { autoaccepted, preempted, preempt } = pagerFixtures;
  h.fetch.mockImplementation(async (url: string) => url.includes('/incidents/') ? new Response(JSON.stringify({ error: { code: 'not_found', message: 'No approved incident example' } }), { status: 404 }) : json(autoaccepted));
  const { qc } = mount();
  const job = await screen.findByRole('region', { name: 'Current job' });
  await waitFor(() => expect(job).toHaveTextContent('wo-0006'));
  expect(screen.getByRole('button', { name: /^Done$/ })).toBeEnabled();
  expect(preempt.displaced).toEqual(preempted.queue[0]);
  expect(preempt.work_order).toEqual(preempted.job?.work_order);
  expect(preempt.technician).toEqual(preempted.technician);
  expect(preempt.work_order.displaced_work_order_id).toBe('wo-0006');
  act(() => Source.all[0]?.emit(preempted));
  await waitFor(() => expect(job).toHaveTextContent('wo-0007'));
  expect(screen.getByText(preempted.job?.why_you ?? '')).toBeInTheDocument();
  const queue = screen.getByRole('region', { name: 'Queued jobs' }); expect(queue).toHaveTextContent('wo-0006'); expect(queue).toHaveTextContent('paused');
  expect(qc.getQueryData<PagerView>(pagerKey('tech-03'))?.technician.current_work_order?.work_order_id).toBe('wo-0007');
  expect(qc.getQueryData<PagerView>(pagerKey('tech-03'))?.technician.path).toEqual(preempted.technician.path);
  act(() => Source.all[0]?.emit(autoaccepted)); expect(qc.getQueryData<PagerView>(pagerKey('tech-03'))?.version).toBe(6);
  expect(posts()).toHaveLength(0);
});
it('draws the exact approved preemption cabinet path including repeated detour waypoints', () => {
  render(<SiteFloor floor={pagerFixtures.floor} halls={[]} technicians={[pagerFixtures.preempted.technician]} selected={null} onSelect={vi.fn()} />);
  expect(document.querySelector('[data-technician-path="tech-03"]')).toHaveAttribute('points', '22,10 22,11.5 21,11.5 22,11.5 22,4.5 25,4.5');
});
it('displays raw anomaly_score model_feature evidence with its threshold, never as probability', async () => {
  const evidence = [{ type: 'model_feature', field: 'anomaly_score', value: 0.73, threshold: 0.6, unit: null, consecutive_readings: null }];
  const incident = { ...fixtures.incidentDetail, evidence, latest_prediction: fixtures.incidentDetail.latest_prediction ? { ...fixtures.incidentDetail.latest_prediction, evidence, score_kind: 'model_score' } : null, score_kind: 'model_score' };
  h.fetch.mockImplementation(async (url: string) => json(url.includes('/models') ? fixtures.modelsList : url.includes('/readings') ? { items: [], total: 0 } : url.endsWith('/whatif') ? {} : incident));
  mount(<IncidentDetailPage id={incident.incident_id} />); const table = await screen.findByRole('table', { name: 'Evidence' });
  const row = within(table).getAllByRole('row')[1]; expect(row).toHaveTextContent('model_feature'); expect(row).toHaveTextContent('anomaly_score'); expect(row).toHaveTextContent('0.73'); expect(row).toHaveTextContent('0.6'); expect(row).not.toHaveTextContent(/probability|%/i);
});