import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
const h = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('@/api/client', async (original) => { const m = await original<typeof import('@/api/client')>(); return { ...m, DATA_MODE: 'live', api: m.createLiveClient('/api/v1', (...args) => h.fetch(...args)) }; });
import { createLiveClient } from '@/api/client';
import { partsFixtures as f } from '@/api/parts-fixtures';
import { gpuFixtures as g } from '@/api/gpu-fixtures';
import { fixtures } from '@/api/fixtures';
import { fleetFixtures } from '@/api/fleet-fixtures';
import { opsFixtures } from '@/api/ops-fixtures';
import { serverComponentQuery, serverComponentsQuery } from '@/api/parts-queries';
import { componentPath, metricUnit, rackPath, serverPath } from '@/api/parts-types';
import { ComponentPage } from '@/pages/ComponentPage';
import { RackPage } from '@/pages/RackPage';
import { ServerParts } from '@/components/ServerParts';
import { ServerFaultControl } from '@/components/ServerFaultControl';
import { FailureModePanel } from '@/components/FailureModePanel';
import { IncidentDetailPage } from '@/pages/IncidentDetailPage';
const json = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status });
function mount(c: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return { qc, view: render(<QueryClientProvider client={qc}>{c}</QueryClientProvider>) };
}
beforeEach(() => { h.fetch.mockReset(); });
it('encodes both IDs and uses exact list and 60-sample detail requests, distinct keys and 1s polling', async () => {
  h.fetch.mockImplementation(async () => json(f.component)); const c = createLiveClient('/api/v1', h.fetch);
  await c.fleetServerComponents('a/b #'); await c.fleetServerComponent('a/b #', 'fan/5 #');
  expect(h.fetch.mock.calls.map(([u]) => u)).toEqual(['/api/v1/fleet/servers/a%2Fb%20%23/components', '/api/v1/fleet/servers/a%2Fb%20%23/components/fan%2F5%20%23?history=60']);
  expect(serverComponentsQuery('a').queryKey).not.toEqual(serverComponentQuery('a', 'b').queryKey);
  expect(serverComponentQuery('a', 'b').queryKey).not.toEqual(serverComponentQuery('b', 'b').queryKey);
  expect(serverComponentQuery('a', 'b').refetchInterval).toBe(1000); expect(serverComponentsQuery('a').refetchInterval).toBe(1000);
  expect(componentPath('a/b #', 'fan/5 #')).toBe('/fleet/servers/a%2Fb%20%23/components/fan%2F5%20%23');
  expect(serverPath('a/b #')).toBe('/fleet/servers/a%2Fb%20%23'); expect(rackPath('a/b #')).toBe('/fleet/racks/a%2Fb%20%23');
});
it.each([['temp_c','°C'],['clock_pct','%'],['util_pct','%'],['wear_pct','%'],['ecc_errors','count'],['crc_errors','count'],['rpm','rpm'],['watts','W'],['link_up','binary 0/1'],['ok','binary 0/1'],['vendor_metric',null]])('uses only agreed %s unit %s', (metric, unit) => expect(metricUnit(metric)).toBe(unit));
it('updates returned diagram values and statuses while mounted without mutations', async () => {
  let response = f.components; h.fetch.mockImplementation(async () => json(response));
  const { qc } = mount(<ServerParts id={f.components.server_id} />); const region = await screen.findByRole('region', { name: 'Server parts' });
  expect(within(region).getAllByRole('link')).toHaveLength(39);
  response = { ...f.components, observed_at: '2026-11-08T09:00:00Z', components: f.components.components.map((c) => c.component_id === 'fan5' ? { ...c, status: 'failed', metrics: { rpm: 0 } } : c) };
  await act(async () => { await qc.invalidateQueries({ queryKey: serverComponentsQuery(f.components.server_id).queryKey }); });
  const fan = region.querySelector('a[href="/fleet/servers/srv-A1-01-1/components/fan5"]');
  await waitFor(() => expect(fan).toHaveTextContent('failed'));
  expect(fan).toHaveTextContent('0 rpm'); expect(region).toHaveTextContent(response.observed_at ?? '');
  expect(h.fetch.mock.calls.every(([, i]) => !i?.method)).toBe(true);
});
it('updates part metric, playbook and observed time while mounted; retains parent rack navigation', async () => {
  let response = f.component;
  h.fetch.mockImplementation(async (u: string) => json(u.includes('/components/') ? response : g.server));
  const { qc } = mount(<ComponentPage id={f.component.server_id} cid="fan5" />);
  expect(await screen.findByRole('heading', { level: 1, name: 'Fan 5' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Parent server/ })).toHaveAttribute('href', '/fleet/servers/srv-A1-01-1');
  expect(await screen.findByRole('link', { name: 'Rack B1-04' })).toHaveAttribute('href', '/fleet/racks/B1-04');
  response = { ...response, component: { ...response.component, status: 'failed', metrics: { rpm: 0 } }, history: [...response.history, { observed_at: '2026-11-08T09:00:00Z', status: 'failed', metrics: { rpm: 0 } }], failure_mode: { ...f.component.failure_mode, mode_id: 'returned-new-mode', title: 'New backend title', cause: 'New backend cause', reasoning: 'New backend reasoning', steps: ['New backend step'], signals: [], evidence: {}, repair_hours: 0, parts_cost_usd: 0 } };
  await act(async () => { await qc.invalidateQueries({ queryKey: serverComponentQuery(f.component.server_id, 'fan5').queryKey }); });
  await screen.findByText('New backend cause'); expect(screen.getByText('New backend reasoning')).toBeInTheDocument(); expect(screen.getByText('New backend step')).toBeInTheDocument();
  expect(screen.getByText('0 USD')).toBeInTheDocument(); expect(screen.getByText('0 h')).toBeInTheDocument(); expect(screen.getByText('Status: failed')).toBeInTheDocument();
  expect(screen.getAllByText('2026-11-08T09:00:00Z').length).toBeGreaterThan(0);
  expect(h.fetch.mock.calls.every(([, i]) => !i?.method)).toBe(true);
});
it('preserves per-metric missing gaps, zero, null, history-only metrics and unknown units without inventing samples', async () => {
  const detail = { ...f.component, failure_mode: null, component: { ...f.component.component, metrics: { temp_c: 0, rpm: null, vendor_metric: 8, ok: 0 } }, history: [
    { observed_at: '2026-11-08T08:00:00Z', status: 'ok', metrics: { temp_c: 0, rpm: 0, ecc_errors: 0 } },
    { observed_at: '2026-11-08T08:00:01Z', status: 'warning', metrics: {} },
    { observed_at: '2026-11-08T08:00:02Z', status: 'failed', metrics: { temp_c: null, rpm: 20 } },
  ] };
  h.fetch.mockImplementation(async (u: string) => json(u.includes('/components/') ? detail : g.server)); mount(<ComponentPage id="s" cid="c" />);
  const table = await screen.findByRole('table', { name: 'Part history' }); expect(within(table).getAllByRole('row')).toHaveLength(4);
  const rows = within(table).getAllByRole('row'); expect(rows[1]).toHaveTextContent('0'); expect(within(rows[2] as HTMLElement).getAllByText('Not reported')).toHaveLength(5);
  expect(screen.getByRole('img', { name: 'temp_c (°C) over time, 3 readings' })).toBeInTheDocument();
  expect(screen.getByRole('img', { name: 'ecc_errors (count) over time, 3 readings' })).toBeInTheDocument();
  expect(screen.getAllByText(/unit not provided/).length).toBeGreaterThan(0); expect(screen.getByText('Failure mode: Not reported')).toBeInTheDocument();
});
it('keeps empty histories honest and nullable repair costs uncomputed', async () => {
  h.fetch.mockImplementation(async (u: string) => json(u.includes('/components/') ? { ...f.component, component: { ...f.component.component, metrics: {} }, history: [], failure_mode: null } : g.server));
  mount(<ComponentPage id="s" cid="c" />); expect(await screen.findByText('No history returned.')).toBeInTheDocument(); expect(screen.queryByRole('img')).not.toBeInTheDocument();
});
it.each(['SERVER_NOT_FOUND', 'COMPONENT_NOT_FOUND'])('preserves exact %s envelope and request ID without fallback', async (code) => {
  h.fetch.mockImplementation(async (u: string) => u.includes('/components/') ? json({ error: { code, message: 'Exact backend message', details: { id: 'missing' }, request_id: 'parts-req-77' } }, 404) : json(g.server));
  mount(<ComponentPage id="missing" cid="missing" />); expect(await screen.findByText(/parts-req-77/)).toHaveTextContent(code); expect(screen.getByText('Exact backend message')).toBeInTheDocument();
  expect(screen.queryByRole('region', { name: 'Failure mode' })).not.toBeInTheDocument();
});
it('refreshes incident playbook and displays exact returned costs/scores, never a frontend diagnosis', async () => {
  let incident = f.incident;
  h.fetch.mockImplementation(async (u: string) => json(u.includes('/incidents/') && !u.endsWith('/whatif') ? incident : u.includes('/models') ? fixtures.modelsList : u.includes('/readings') ? { items: [], total: 0 } : u.endsWith('/whatif') ? g.whatif : opsFixtures.technicians));
  const { qc } = mount(<IncidentDetailPage id="inc-000793" />); await screen.findByText(f.incident.failure_mode?.cause ?? '');
  expect(screen.getByText('80 USD')).toBeInTheDocument(); expect(screen.getByText('0.5 h')).toBeInTheDocument(); expect(screen.getByText('0.55')).toBeInTheDocument(); expect(screen.getAllByText('$3,600').length).toBeGreaterThan(0);
  incident = { ...incident, failure_mode: { ...f.component.failure_mode, mode_id: 'm', title: 'Changed mode', cause: 'Mounted incident cause changed', reasoning: 'Returned reasoning changed', signals: [], steps: ['Returned replacement step'], evidence: { min_fan_rpm: 0 }, repair_hours: null, parts_cost_usd: null } };
  await act(async () => { await qc.invalidateQueries({ queryKey: ['incident', 'inc-000793'] }); }); await screen.findByText('Mounted incident cause changed');
  expect(screen.queryByText('80 USD')).not.toBeInTheDocument(); expect(screen.getByText('Returned replacement step')).toBeInTheDocument();
  expect(h.fetch.mock.calls.every(([, i]) => !i?.method)).toBe(true);
});
it('uses only the actual returned rack machines, server IDs, cooling and incidents', async () => {
  h.fetch.mockImplementation(async () => json(fleetFixtures.rack)); mount(<RackPage id={fleetFixtures.rack.rack_id} />);
  const link = await screen.findByRole('link', { name: 'Open rack A1-03' }); expect(link).toHaveAttribute('href', '/fleet/racks/A1-03');
  for (const id of fleetFixtures.rack.server_ids ?? []) expect(screen.getAllByRole('link', { name: id })[0]).toHaveAttribute('href', serverPath(id));
  expect(screen.queryByRole('region', { name: /Equipment details/ })).not.toBeInTheDocument();
  expect(screen.getAllByText('Not reported').length).toBeGreaterThanOrEqual(2);
  expect(h.fetch.mock.calls[0]?.[0]).toBe('/api/v1/fleet/racks/A1-03?history=30');
});
it.each(['memory_fault','nic_failure','server_fan_failure'])('POSTs exact merged %s kind only on click and locks duplicates', async (kind) => {
  let finish: ((r: Response) => void) | undefined;
  h.fetch.mockImplementation(() => new Promise<Response>((r) => { finish = r; }));
  mount(<ServerFaultControl servers={[g.server.machine, { ...g.server.machine, asset_id: 'not-server', asset_type: 'cooling_unit' }]} selectedServerId={g.server.machine.asset_id} />);
  expect(h.fetch).not.toHaveBeenCalled(); expect(screen.queryByRole('option', { name: /not-server/ })).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole('combobox', { name: 'Server fault choice' }), { target: { value: kind } });
  const b = screen.getByRole('button', { name: 'Inject server fault' }); fireEvent.click(b); fireEvent.click(b);
  await waitFor(() => expect(h.fetch).toHaveBeenCalledTimes(1)); expect(JSON.parse(h.fetch.mock.calls[0]?.[1].body)).toEqual({ asset_ids: [g.server.machine.asset_id], kind });
  expect(screen.getByRole('button', { name: 'Injecting…' })).toBeDisabled();
  finish?.(json({ error: { code: 'FAULT_KIND_NOT_SUPPORTED', message: 'Unsupported returned target', request_id: 'fault-77' } }, 422));
  expect(await screen.findByText(/fault-77/)).toHaveTextContent('FAULT_KIND_NOT_SUPPORTED');
});