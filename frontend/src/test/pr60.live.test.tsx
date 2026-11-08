import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
const h = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('@/api/client', async (orig) => { const m = await orig<typeof import('@/api/client')>(); return { ...m, DATA_MODE: 'live', api: m.createLiveClient('/api/v1', (...a) => h.fetch(...a)) }; });
import { ServerFaultControl } from '@/components/ServerFaultControl';
import { PriorityRank } from '@/components/PriorityRank';
import { OperationsPage } from '@/pages/OperationsPage';
import { IncidentDetailPage } from '@/pages/IncidentDetailPage';
import { FleetPage } from '@/pages/FleetPage';
import { ServerPage } from '@/pages/ServerPage';
import { PagerPage } from '@/pages/PagerPage';
import { IncidentsPage } from '@/pages/IncidentsPage';
import { pagerFixtures } from '@/api/pager-fixtures';
import { pagerKey } from '@/api/ops-stream';
import type { PagerView } from '@/api/ops-types';
import { gpuFixtures as g } from '@/api/gpu-fixtures';
import { fleetFixtures as f } from '@/api/fleet-fixtures';
import { fixtures } from '@/api/fixtures';
import { opsFixtures as o } from '@/api/ops-fixtures';
import type { OpsWorkOrder } from '@/api/ops-types';
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const server = { ...g.server.machine, asset_id: 'actual-returned/server-99', name: 'Returned GPU server' };
function mount(node: React.ReactNode) { const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } }); return { qc, view: render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>) }; }
beforeEach(() => { h.fetch.mockReset(); vi.stubGlobal('EventSource', class { readyState = 0; addEventListener() {} removeEventListener() {} close() {} }); });

it.each([['GPU fails', 'gpu_fault'], ['Whole server down', 'server_crash']])('sends exact selected inventory ID and %s kind with no automatic mutation', async (label, kind) => {
  let finish: ((r: Response) => void) | undefined;
  h.fetch.mockImplementation(() => new Promise<Response>((r) => { finish = r; }));
  mount(<ServerFaultControl servers={[server, { ...server, asset_type: 'cooling_unit', asset_id: 'not-a-server' }]} />);
  expect(h.fetch).not.toHaveBeenCalled(); expect(screen.queryByRole('option', { name: /not-a-server/ })).not.toBeInTheDocument();
  expect(screen.getByRole('button')).toBeDisabled();
  fireEvent.change(screen.getByLabelText('GPU server'), { target: { value: server.asset_id } });
  fireEvent.change(screen.getByLabelText('Server fault choice'), { target: { value: kind } });
  expect(screen.getByRole('option', { name: label })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button')); fireEvent.click(screen.getByRole('button'));
  await waitFor(() => expect(h.fetch).toHaveBeenCalledOnce());
  expect(JSON.parse(h.fetch.mock.calls[0]?.[1].body)).toEqual({ asset_ids: [server.asset_id], kind });
  expect(screen.getByRole('button')).toBeDisabled();
  finish?.(json({ error: { code: 'FAULT_KIND_NOT_SUPPORTED', message: 'Fault does not suit selected asset', request_id: 'fault-422' } }, 422));
  expect(await screen.findByText(/fault-422/)).toBeInTheDocument(); expect(screen.getByText(/FAULT_KIND_NOT_SUPPORTED/)).toBeInTheDocument(); expect(screen.getByRole('button')).toBeEnabled();
});
it('blocks empty/loading/failed inventory without constructing server IDs', () => {
  const { view } = mount(<ServerFaultControl servers={[]} loading />);
  expect(screen.getByRole('button')).toBeDisabled(); expect(screen.getByText('Loading GPU server inventory…')).toBeInTheDocument();
  view.unmount(); mount(<ServerFaultControl servers={[]} />); expect(screen.getByText('No GPU servers returned.')).toBeInTheDocument(); expect(screen.getByRole('button')).toBeDisabled(); expect(h.fetch).not.toHaveBeenCalled();
});
it('makes returned server choices available on Fleet and targets exact selection', async () => {
  h.fetch.mockImplementation(async (url: string, init?: RequestInit) => json(init?.method === 'POST' ? { injected: [], live: f.status.live } : url.includes('/sites') ? f.sites : url.includes('/status') ? { ...f.status, machines: [server] } : f.map));
  mount(<FleetPage site="datacenter" onSiteChange={vi.fn()} />);
  await screen.findByRole('option', { name: `Returned GPU server (${server.asset_id})` });
  fireEvent.change(screen.getByLabelText('GPU server'), { target: { value: server.asset_id } });
  fireEvent.change(screen.getByLabelText('Server fault choice'), { target: { value: 'server_crash' } });
  fireEvent.click(screen.getByRole('button', { name: 'Inject server fault' }));
  await waitFor(() => expect(h.fetch.mock.calls.filter(([, i]) => i?.method === 'POST')).toHaveLength(1));
  const post = h.fetch.mock.calls.find(([, i]) => i?.method === 'POST'); expect(JSON.parse(post?.[1].body)).toEqual({ asset_ids: [server.asset_id], kind: 'server_crash' });
});
it('fetches a referenced incident directly beyond list limits and refreshes returned rank without converting index', async () => {
  let rank: number | null = 4;
  h.fetch.mockImplementation(async () => json({ ...fixtures.incidentDetail, priority_rank: rank, priority_index: 0.99 }));
  mount(<PriorityRank incidentId="outside/page" />);
  expect(await screen.findByText('4')).toBeInTheDocument(); expect(h.fetch.mock.calls[0]?.[0]).toBe('/api/v1/incidents/outside%2Fpage');
  rank = 1; await screen.findByText('1', {}, { timeout: 2500 });
  rank = null; await screen.findByText('Not reported', {}, { timeout: 2500 });
});
it('reports rank lookup errors and request IDs rather than fabricating rank', async () => {
  h.fetch.mockResolvedValue(json({ error: { code: 'LOOKUP_FAILED', message: 'Unavailable', request_id: 'rank-rid' } }, 503));
  mount(<PriorityRank incidentId="missing" />); expect(await screen.findByText(/rank-rid/)).toBeInTheDocument(); expect(screen.getByRole('alert')).toHaveTextContent('Rank unavailable');
});
it('updates list ranks in returned order and preserves missing-rank honesty', async () => {
  let rank = 5;
  h.fetch.mockImplementation(async () => json({ ...fixtures.incidentsList, items: [{ ...fixtures.incidentsList.items[0], incident_id: 'low-first', title: 'First returned', priority_rank: rank, priority_index: 0.99 }, { ...fixtures.incidentsList.items[0], incident_id: 'missing', title: 'Missing rank', priority_rank: null }] }));
  mount(<IncidentsPage />); expect(await screen.findByText('5')).toBeInTheDocument(); expect(screen.getByText('Not reported')).toBeInTheDocument(); rank = 1;
  await waitFor(() => expect(screen.getAllByRole('row')[1]?.querySelector('td')).toHaveTextContent('1'), { timeout: 2500 });
  expect(screen.getAllByRole('row').slice(1).map((r) => r.textContent)).toEqual([expect.stringContaining('First returned'), expect.stringContaining('Missing rank')]);
});
it('keeps pager current/queue ranks live and backend ID order despite stale pager versions', async () => {
  const base = pagerFixtures.paged; if (!base.job) throw new Error('No pager job');
  const first = { ...base.job.work_order, work_order_id: 'queued-first', incident_id: 'rank-first', title: 'First queue job' };
  const second = { ...first, work_order_id: 'queued-second', incident_id: 'rank-second', title: 'Second queue job' };
  const current: PagerView = { ...base, version: 50, technician: { ...base.technician, queued_work_order_ids: ['queued-first', 'absent', 'queued-second'] }, job: { ...base.job, incident_id: 'rank-first' }, queue: [second, first] };
  let rank = 4;
  h.fetch.mockImplementation(async (u: string) => json(u.includes('/incidents/') ? { ...fixtures.incidentDetail, priority_rank: u.endsWith('rank-second') ? 1 : rank } : current));
  const { qc } = mount(<PagerPage onTechnicianChange={vi.fn()} />);
  await waitFor(() => expect(screen.getAllByText('4')).toHaveLength(2));
  const table = screen.getByRole('table'); expect(within(table).getAllByRole('row').slice(1).map((r) => r.textContent)).toEqual([expect.stringContaining('queued-first'), expect.stringContaining('absent'), expect.stringContaining('queued-second')]);
  h.fetch.mockImplementation(async (u: string) => json(u.includes('/incidents/') ? { ...fixtures.incidentDetail, priority_rank: rank } : { ...base, version: 2 }));
  await act(async () => { await qc.invalidateQueries({ queryKey: pagerKey('tech-03') }); });
  expect(qc.getQueryData<PagerView>(pagerKey('tech-03'))?.version).toBe(50); expect(within(table).getByText('queued-first')).toBeInTheDocument();
  rank = 1; await waitFor(() => expect(screen.queryAllByText('4')).toHaveLength(0), { timeout: 2500 }); expect(screen.getAllByText('1')).toHaveLength(3);
  expect(h.fetch.mock.calls.filter(([, i]) => i?.method === 'POST')).toHaveLength(0);
});
it('updates incident detail rank while mounted on medium to high escalation without dispatch', async () => {
  let rank = 3;
  h.fetch.mockImplementation(async (url: string) => json(url.endsWith('/incidents/inc-demo-001') ? { ...fixtures.incidentDetail, risk_level: rank === 1 ? 'high' : 'medium', priority_rank: rank } : url.endsWith('/models') ? fixtures.modelsList : url.endsWith('/whatif') ? o.whatif : url.includes('/technicians') ? o.technicians : fixtures.assetReadings));
  mount(<IncidentDetailPage id="inc-demo-001" />);
  const section = (await screen.findByText('Priority', { selector: 'h2' })).closest('section'); if (!section) throw new Error('No priority section');
  expect(await within(section).findByText('3')).toBeInTheDocument(); rank = 1;
  expect(await within(section).findByText('1', {}, { timeout: 2500 })).toBeInTheDocument();
  expect(h.fetch.mock.calls.filter(([, i]) => i?.method === 'POST')).toHaveLength(0);
});
it('joins plan/current task/queued IDs to authoritative ranks and preserves backend queue order', async () => {
  const base = o.technicians.work_orders[0]; if (!base) throw new Error('No work order');
  const a: OpsWorkOrder = { ...base, work_order_id: 'wo-first', title: 'Backend first', incident_id: 'inc-first', status: 'paged' };
  const b: OpsWorkOrder = { ...base, work_order_id: 'wo-second', title: 'Backend second', incident_id: 'inc-second', status: 'awaiting_confirmation' };
  let rank = 4;
  h.fetch.mockImplementation(async (url: string) => json(url.includes('/incidents/') ? { ...fixtures.incidentDetail, priority_rank: url.endsWith('inc-second') ? 1 : rank } : url.includes('/plan') ? { ...o.plan, items: [{ ...o.plan.items[0], incident_id: 'inc-first' }] } : url.includes('/technicians') ? { ...o.technicians, technicians: [{ ...o.technicians.technicians[0], current_work_order: a, queued_work_order_ids: ['wo-first', 'wo-missing', 'wo-second'] }], work_orders: [b, a] } : url.includes('/matrix') ? o.matrix : o.cases));
  mount(<OperationsPage site="datacenter" onSiteChange={vi.fn()} />);
  await waitFor(() => expect(screen.getAllByText('4').length).toBeGreaterThanOrEqual(3));
  const queue = screen.getByRole('list'); expect(within(queue).getAllByRole('listitem').map((li) => li.textContent)).toEqual([expect.stringContaining('wo-first'), expect.stringContaining('wo-missing'), expect.stringContaining('wo-second')]);
  expect(within(queue).getByText('Work order not reported')).toBeInTheDocument(); expect(within(queue).getByText('Not reported')).toBeInTheDocument();
  rank = 1; await waitFor(() => expect(screen.queryAllByText('4')).toHaveLength(0), { timeout: 2500 });
  expect(screen.getAllByText('1').length).toBeGreaterThanOrEqual(3); expect(h.fetch.mock.calls.filter(([, i]) => i?.method === 'POST')).toHaveLength(0);
});
it.each(['paged', 'awaiting_confirmation'] as const)('keeps fleet/server/GPU usable with returned %s work order', async (status) => {
  const machine = { ...g.server.machine, work_order: { work_order_id: 'wo-live', technician_id: 'tech-03', technician_name: 'Sam', status, option: 'fix_now', progress: 0, eta_minutes: 12 } };
  h.fetch.mockImplementation(async () => json({ ...g.server, machine })); mount(<ServerPage id={machine.asset_id} gpuIndex={7} onGpuChange={vi.fn()} />);
  expect(await screen.findByRole('region', { name: 'GPU 7 detail' })).toBeInTheDocument(); expect(screen.getAllByText(new RegExp(status)).length).toBeGreaterThan(0); expect(screen.getByRole('combobox', { name: 'Server fault choice' })).toBeEnabled();
});