import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
const h = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('@/api/client', async (orig) => { const m = await orig<typeof import('@/api/client')>(); return { ...m, api: m.createLiveClient('http://t/api/v1', (...a) => h.fetch(...a)), DATA_MODE: 'live' }; });
import { createFixtureClient, createLiveClient } from '@/api/client';
import { gpuFixtures as g } from '@/api/gpu-fixtures';
import { fleetFixtures as f } from '@/api/fleet-fixtures';
import { serverQuery } from '@/api/gpu-queries';
import { fleetRackQuery } from '@/api/fleet-queries';
import { listAllAssets } from '@/api/all-assets';
import { ServerPage } from '@/pages/ServerPage';
import { SimulatePage } from '@/pages/SimulatePage';
import { AssetsPage } from '@/pages/AssetsPage';
import { FleetRackPane } from '@/components/FleetWorkspace';
import { GpuJobs } from '@/components/GpuJobs';
import { fixtures } from '@/api/fixtures';
const json = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status });
function mount(c: React.ReactNode) { const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } }); const wrap = (x: React.ReactNode) => <QueryClientProvider client={qc}>{x}</QueryClientProvider>; return { view: render(wrap(c)), wrap }; }
beforeEach(() => { h.fetch.mockReset(); h.fetch.mockImplementation(async () => json(g.server)); });
it('encodes server/rack IDs, uses distinct keys and polls servers every second', async () => {
  const c = createLiveClient('http://t/api/v1', (...a) => h.fetch(...a)); await c.fleetServer('a/b #'); await c.fleetRack('a/b #');
  expect(h.fetch.mock.calls.map(([u]) => u)).toEqual(['http://t/api/v1/fleet/servers/a%2Fb%20%23?history=30', 'http://t/api/v1/fleet/racks/a%2Fb%20%23?history=30']);
  expect(serverQuery('x').queryKey).not.toEqual(fleetRackQuery('datacenter', 'x').queryKey); expect(serverQuery('x').refetchInterval).toBe(1000);
});
it('uses exact server/crashed fixtures and disables targeted fixture faults', async () => {
  const c = createFixtureClient(); expect(await c.fleetServer(g.server.machine.asset_id)).toEqual(g.server); expect(await c.fleetServer(g.crashed.machine.asset_id)).toEqual(g.crashed);
  await expect(c.fleetServer('missing')).rejects.toMatchObject({ status: 404 });
  await expect(c.injectFaults({ count: 1, site: 'datacenter', asset_ids: [g.server.machine.asset_id] })).rejects.toMatchObject({ code: 'fixture_mode' });
  expect(await c.incidentWhatIf(g.whatif.incident_id)).toEqual(g.whatif);
});
it('renders all returned GPUs, selects real indices and preserves returned throttling rather than deriving it', async () => {
  const change = vi.fn(); const { view, wrap } = mount(<ServerPage id={g.server.machine.asset_id} gpuIndex={1} onGpuChange={change} />);
  await screen.findByRole('region', { name: 'GPU 1 detail' });
  const first = screen.getByRole('region', { name: 'GPU 1 detail' }); expect(within(first).getByText('ok')).toBeInTheDocument(); expect(within(first).getByText('83.1 °C')).toBeInTheDocument(); expect(within(first).getByText('83 °C')).toBeInTheDocument();
  expect(screen.getAllByRole('tab')).toHaveLength(8); fireEvent.click(screen.getByRole('tab', { name: 'GPU 7 · throttling' })); expect(change).toHaveBeenCalledWith(7);
  view.rerender(wrap(<ServerPage id={g.server.machine.asset_id} gpuIndex={7} onGpuChange={change} />));
  const selected = await screen.findByRole('region', { name: 'GPU 7 detail' }); expect(within(selected).getByText('87.1 %')).toBeInTheDocument(); expect(within(selected).getByText('84.3 °C')).toBeInTheDocument();
});
it('shows nulls/no_data, rejects unreturned GPU index and never fabricates GPU histories', async () => {
  h.fetch.mockResolvedValue(json({ ...g.server, online: null, inlet_temp_c: null, psus_ok: null, ecc_errors: null, power_w: null, machine: { ...g.server.machine, history: [] }, gpus: [{ index: 11, temp_c: null, clock_pct: null, status: 'no_data', throttle_c: 83 }] }));
  const { view, wrap } = mount(<ServerPage id="s" gpuIndex={11} onGpuChange={() => {}} />);
  const selected = await screen.findByRole('region', { name: 'GPU 11 detail' }); expect(within(selected).getByText('no_data')).toBeInTheDocument(); expect(within(selected).getByText('Not reported °C')).toBeInTheDocument(); expect(within(selected).getByText(/GPU history unavailable/)).toBeInTheDocument();
  view.rerender(wrap(<ServerPage id="s" gpuIndex={7} onGpuChange={() => {}} />)); expect(screen.getByText('GPU 7 is not returned by this server.')).toBeInTheDocument();
});
it('shows offline crashed server, incident link, power and exact backend job loss', async () => {
  h.fetch.mockResolvedValue(json(g.crashed)); mount(<ServerPage id={g.crashed.machine.asset_id} gpuIndex={1} onGpuChange={() => {}} />);
  const selected = await screen.findByRole('region', { name: 'GPU 1 detail' }); expect(within(selected).getByText('offline')).toBeInTheDocument(); expect(within(selected).getByText('0 %')).toBeInTheDocument();
  expect(screen.getAllByRole('link', { name: 'inc-001849' })[0]).toHaveAttribute('href', '/incidents/inc-001849');
  expect(screen.getByText('400')).toBeInTheDocument(); expect(screen.getAllByText('Power: on').length).toBeGreaterThan(0);
});
it.each([404, 503])('shows real server %s errors with request ID and no fixture fallback', async (status) => {
  h.fetch.mockResolvedValue(json({ error: { code: 'SERVER_NOT_FOUND', message: 'GPU endpoint unavailable', request_id: 'gpu-req' } }, status)); mount(<ServerPage id="missing" gpuIndex={undefined} onGpuChange={() => {}} />);
  expect(await screen.findByText(/gpu-req/)).toBeInTheDocument(); expect(screen.queryByRole('tab')).not.toBeInTheDocument();
});
it('targets explicit GPU fault with a kind selector and blocks duplicate pending requests', async () => {
  let finish: ((r: Response) => void) | undefined;
  h.fetch.mockImplementation(async (_u: string, init?: RequestInit) => init?.method === 'POST' ? new Promise<Response>((r) => { finish = r; }) : json(g.server));
  mount(<ServerPage id={g.server.machine.asset_id} gpuIndex={1} onGpuChange={() => {}} />);
  const b = await screen.findByRole('button', { name: 'Inject server fault' }); fireEvent.click(b); expect(await screen.findByRole('button', { name: 'Injecting…' })).toBeDisabled();
  const calls = h.fetch.mock.calls.filter(([, i]) => i?.method === 'POST'); expect(calls).toHaveLength(1); expect(JSON.parse(calls[0]?.[1].body)).toEqual({ asset_ids: ['srv-B1-04-3'], kind: 'gpu_fault' });
  finish?.(json({ error: { code: 'FLEET_LIVE_RUNNING', message: 'Conflict', request_id: 'fault-409' } }, 409)); expect(await screen.findByText(/fault-409/)).toBeInTheDocument();
});
it('links returned rack server IDs explicitly and renders exact job reasons/prices without financial calculations', () => {
  mount(<><FleetRackPane rack={f.rack} /><GpuJobs jobs={g.jobs.jobs} /></>);
  for (const id of f.rack.server_ids ?? []) expect(screen.getAllByRole('link', { name: id })[0]).toHaveAttribute('href', `/servers/${id}`);
  expect(screen.getByText('48.96')).toBeVisible(); expect(screen.getByText('84.7 %')).toBeVisible(); expect(screen.getByText("34 GPUs are throttling from heat; the job runs at the slowest GPU's speed")).toBeVisible();
  const prices = screen.getAllByText(/demo price, not an actual bill/);
  expect(prices).toHaveLength(4);
  for (const price of prices) {
    expect(price).not.toBeVisible();
    const details = price.closest('details');
    if (!details) throw new Error('Missing price disclosure');
    fireEvent.click(within(details).getByText('Source details', { selector: 'summary' }));
    expect(price).toBeVisible();
  }
});
function assetsBackend(fail = false) {
  h.fetch.mockImplementation(async (url: string) => {
    const u = new URL(url);
    if (u.pathname.endsWith('/assets')) {
      const offset = Number(u.searchParams.get('offset')); const limit = Number(u.searchParams.get('limit'));
      if (fail && offset > 0) return json({ error: { code: 'FAIL', message: 'Page failed', request_id: 'page-2' } }, 503);
      return json({ items: Array.from({ length: Math.min(limit, 262 - offset) }, (_, n) => ({ ...fixtures.assetsList.items[0], asset_id: `asset-${offset+n}`, name: `Equipment ${offset+n}`, compatible_detector: offset+n === 240 ? 'cooling-rule-v1' : null })), total: 262, limit, offset });
    }
    if (u.pathname.endsWith('/models')) return json(fixtures.modelsList);
    return json({ items: [], total: 0, limit: 50, offset: 0 });
  });
}
it('paginates all 262 assets and discovers compatible cooling assets beyond 200', async () => {
  assetsBackend(); const c = createLiveClient('http://t/api/v1', (...a) => h.fetch(...a)); const all = await listAllAssets(c); expect(all).toHaveLength(262); expect(all[240]?.compatible_detector).toBe('cooling-rule-v1');
  expect(h.fetch.mock.calls.map(([u]) => u)).toEqual(['http://t/api/v1/assets?limit=200&offset=0', 'http://t/api/v1/assets?limit=200&offset=200']);
  mount(<SimulatePage />); expect(await screen.findByRole('option', { name: 'Equipment 240 (asset-240)' })).toBeInTheDocument();
});
it('reaches the final page of 262 assets without hardcoded totals', async () => {
  assetsBackend(); mount(<AssetsPage />); await screen.findByText('1–50 of 262');
  for (const label of ['51–100 of 262','101–150 of 262','151–200 of 262','201–250 of 262','251–262 of 262']) { fireEvent.click(screen.getByRole('button', { name: 'Next' })); await screen.findByText(label); }
  expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
});
it('surfaces any pagination page failure without partial selectable assets', async () => {
  assetsBackend(true); mount(<SimulatePage />); expect(await screen.findByText(/page-2/)).toBeInTheDocument(); expect(screen.queryByRole('option')).not.toBeInTheDocument();
});
it('terminates malformed empty pagination instead of an infinite request loop', async () => {
  const fetcher = vi.fn().mockResolvedValue(json({ items: [], total: 262, limit: 200, offset: 0 }));
  await expect(listAllAssets(createLiveClient('http://t', fetcher))).rejects.toMatchObject({ code: 'INVALID_PAGINATION' }); expect(fetcher).toHaveBeenCalledTimes(1);
});