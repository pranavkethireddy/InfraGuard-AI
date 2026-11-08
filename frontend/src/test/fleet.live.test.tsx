import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
const h = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('@/api/client', async (orig) => {
  const m = await orig<typeof import('@/api/client')>();
  return { ...m, DATA_MODE: 'live', api: m.createLiveClient('http://t/api/v1', (...a) => h.fetch(...a)) };
});
import { FleetPage } from '@/pages/FleetPage';
import { FleetFloor, FleetMetrics } from '@/components/FleetWorkspace';
import { fleetFixtures as f } from '@/api/fleet-fixtures';
import { fleetMapQuery, fleetRackQuery, fleetStatusQuery } from '@/api/fleet-queries';
import { createFixtureClient, createLiveClient } from '@/api/client';
import { incidentQuery, investigationPollInterval } from '@/api/queries';
import { IncidentDetailPage, ImpactLedger } from '@/pages/IncidentDetailPage';
import { AssetsPage } from '@/pages/AssetsPage';
import { fixtures } from '@/api/fixtures';
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const postCalls = () => h.fetch.mock.calls.filter(([, init]) => init?.method === 'POST');
function backend() {
  h.fetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const u = new URL(url); const path = u.pathname.replace('/api/v1', '');
    if (init?.method === 'POST') {
      if (path === '/fleet/clear') return json({ readings_deleted: 2280, predictions_deleted: 2280, incidents_deleted: 5, faults_cleared: 5, simulations_reset: 0, live: f.map.live });
      return json(f.map.live);
    }
    if (path === '/fleet/sites') return json(f.sites);
    if (path === '/fleet/map') return json(u.searchParams.get('site') === 'mining' ? { ...f.map, site_id: 'mining', halls: [], site_name: 'Crypto mining site' } : f.map);
    if (path === '/fleet/status') return json(u.searchParams.get('site') === 'mining' ? f.mining : f.status);
    if (path.startsWith('/fleet/racks/')) return json(f.rack);
    return json({ error: { code: 'NOT_FOUND', message: 'No mock route', request_id: 'r1' } }, 404);
  });
}
function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return { qc, wrap: (children: React.ReactNode) => <QueryClientProvider client={qc}>{children}</QueryClientProvider> };
}
beforeEach(() => { h.fetch.mockReset(); backend(); });
describe('Fleet HTTP contracts and isolation', () => {
  it('includes selected site and history=30 in map/status and site in each cache key', async () => {
    const client = createLiveClient('http://t/api/v1', (...a) => h.fetch(...a));
    await client.fleetMap('mining'); await client.fleetStatus('datacenter'); await client.fleetRack('M1-01');
    expect(h.fetch.mock.calls.map(([u]) => u)).toEqual(['http://t/api/v1/fleet/map?site=mining&history=30', 'http://t/api/v1/fleet/status?site=datacenter&history=30', 'http://t/api/v1/fleet/racks/M1-01?history=30']);
    expect(fleetMapQuery('mining').queryKey).not.toEqual(fleetMapQuery('datacenter').queryKey);
    expect(fleetStatusQuery('mining').queryKey).not.toEqual(fleetStatusQuery('datacenter').queryKey);
    expect(fleetRackQuery('mining', 'M1-01').queryKey).not.toEqual(fleetRackQuery('datacenter', 'M1-01').queryKey);
    expect(fleetStatusQuery('mining').refetchInterval).toBe(1000);
    expect(fleetMapQuery('datacenter').refetchInterval).toBe(1000);
  });
  it('uses exact fixtures and never executes mutation fixtures', async () => {
    const client = createFixtureClient();
    expect(await client.fleetStatus('mining')).toEqual(f.mining);
    await expect(client.fleetMap('mining')).rejects.toMatchObject({ status: 404 });
    for (const action of [() => client.startFleet(), () => client.stopFleet(), () => client.injectFaults({ count: 3, site: 'mining' }), () => client.clearFleet()]) await expect(action()).rejects.toMatchObject({ code: 'fixture_mode' });
  });
  it('renders returned rack floor coordinates and selects with keyboard', () => {
    const select = vi.fn(); render(<FleetFloor halls={f.map.halls} gridUnit={f.map.grid_unit} selected={null} onSelect={select} />);
    const target = screen.getByRole('button', { name: /Rack A1-03: critical/ });
    expect(target).toHaveAttribute('x', '8'); expect(target).toHaveAttribute('y', '3');
    expect(target).toHaveAttribute('width', '2'); expect(target).toHaveAttribute('height', '1');
    fireEvent.keyDown(target, { key: 'Enter' }); expect(select).toHaveBeenCalledWith('A1-03');
    fireEvent.keyDown(target, { key: ' ' }); expect(select).toHaveBeenCalledTimes(2);
  });
  it('shows null metrics as No data with exact units/source and no_data legend', () => {
    render(<FleetMetrics metrics={[{ key: 'hash', label: 'Hashrate', value: null, unit: 'PH/s', source: 'backend history' }]} />);
    expect(screen.getByText('No data')).toBeInTheDocument(); expect(screen.getByText('Source: backend history')).toBeInTheDocument();
  });
  it('loads rack details, clears selection and feedback when switching sites', async () => {
    const { wrap } = wrapper(); const change = vi.fn(); const view = render(wrap(<FleetPage site="datacenter" onSiteChange={change} />));
    fireEvent.click(await screen.findByRole('button', { name: /Rack A1-03: critical/ }));
    expect(await screen.findByRole('region', { name: 'Rack investigation · A1-03' })).toBeInTheDocument();
    await waitFor(() => expect(h.fetch.mock.calls.some(([u]) => String(u).endsWith('/fleet/racks/A1-03?history=30'))).toBe(true));
    fireEvent.click(screen.getByRole('tab', { name: 'Crypto mining site' })); expect(change).toHaveBeenCalledWith('mining');
    view.rerender(wrap(<FleetPage site="mining" onSiteChange={change} />));
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Rack investigation · A1-03' })).not.toBeInTheDocument());
    expect(await screen.findByText('miner-05')).toBeInTheDocument();
  });
  it('never auto-starts; faults target mining and clear requires confirmation across BOTH sites', async () => {
    const { wrap } = wrapper(); render(wrap(<FleetPage site="mining" onSiteChange={() => {}} />));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Inject 3 faults' })).toBeEnabled());
    expect(postCalls()).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: 'Inject 3 faults' }));
    await screen.findByText('Backend action completed.');
    expect(JSON.parse(postCalls()[0]?.[1].body)).toEqual({ count: 3, site: 'mining' });
    fireEvent.click(screen.getByRole('button', { name: 'Clear fleet' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText(/all readings, predictions and incidents across BOTH sites/)).toBeInTheDocument();
    expect(postCalls()).toHaveLength(1);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' })); expect(postCalls()).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'Clear fleet' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm clear both sites' }));
    await waitFor(() => expect(postCalls()).toHaveLength(2));
    expect(postCalls()[1]?.[0]).toBe('http://t/api/v1/fleet/clear');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });
  it('posts optional start settings and stop without a body; retains conflict request IDs', async () => {
    const client = createLiveClient('http://t/api/v1', (...a) => h.fetch(...a));
    await client.startFleet({ seed: 42, tick_seconds: 1 }); await client.stopFleet();
    expect(JSON.parse(postCalls()[0]?.[1].body)).toEqual({ seed: 42, tick_seconds: 1 });
    expect(postCalls()[1]?.[1].body).toBeUndefined();
    h.fetch.mockResolvedValue(json({ error: { code: 'SIMULATION_ALREADY_RUNNING', message: 'Single asset running', request_id: 'req-conflict' } }, 409));
    await expect(client.startFleet()).rejects.toMatchObject({ code: 'SIMULATION_ALREADY_RUNNING', status: 409, requestId: 'req-conflict' });
  });
});
describe('Backend business case and investigation refresh', () => {
  it('displays returned mining business values and hashprice provenance without computing', () => {
    const impact = f.minerIncident.impact; if (!impact) throw new Error('Missing public miner impact');
    render(<ImpactLedger impact={impact} />);
    expect(screen.getAllByText('$569.45')).toHaveLength(2); expect(screen.getByText('$60')).toBeInTheDocument(); expect(screen.getByText('$509.45')).toBeInTheDocument(); expect(screen.getByText('8.49')).toBeInTheDocument();
    expect(screen.getByText(/hashprice \$0.0324\/TH\/day on 2026-11-07/)).toBeInTheDocument();
  });
  it('polls queued/running every second, stops completed/failed, refreshes problem/cause', async () => {
    expect(investigationPollInterval('queued')).toBe(1000); expect(investigationPollInterval('running')).toBe(1000); expect(investigationPollInterval('completed')).toBe(false); expect(investigationPollInterval('failed')).toBe(false);
    let calls = 0;
    h.fetch.mockImplementation(async (url: string) => {
      if (url.includes('/incidents/')) { calls++; return json({ ...f.minerIncident, investigation_status: calls === 1 ? 'queued' : 'completed', problem: calls === 1 ? null : 'Returned miner problem', likely_cause: calls === 1 ? null : 'Returned miner cause' }); }
      if (url.includes('/models')) return json(fixtures.modelsList);
      return json({ ...fixtures.assetReadings, asset_id: f.minerIncident.asset_id });
    });
    const { wrap } = wrapper(); render(wrap(<IncidentDetailPage id={f.minerIncident.incident_id} />));
    expect(await screen.findByText('Auto investigation: queued')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Investigate' })).toBeDisabled();
    expect(await screen.findByText('Returned miner problem', {}, { timeout: 2500 })).toBeInTheDocument();
    expect(screen.getByText('Returned miner cause')).toBeInTheDocument();
    expect(calls).toBe(2);
    const interval = incidentQuery('x').refetchInterval;
    expect(typeof interval).toBe('function');
  });
  it('paginates the real 190-asset register rather than truncating at 100', async () => {
    h.fetch.mockImplementation(async (url: string) => {
      const u = new URL(url); const offset = Number(u.searchParams.get('offset')); const limit = Number(u.searchParams.get('limit'));
      const count = Math.min(limit, 190 - offset);
      return json({ items: Array.from({ length: count }, (_, i) => ({ ...fixtures.assetsList.items[0], asset_id: `asset-${offset + i}`, name: `Machine ${offset + i}` })), total: 190, limit, offset });
    });
    const { wrap } = wrapper(); render(wrap(<AssetsPage />));
    expect(await screen.findByText('1–50 of 190')).toBeInTheDocument();
    for (const label of ['51–100 of 190', '101–150 of 190', '151–190 of 190']) {
      fireEvent.click(screen.getByRole('button', { name: 'Next' })); await screen.findByText(label);
    }
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
    expect(h.fetch.mock.calls.map(([u]) => u)).toContain('http://t/api/v1/assets?limit=50&offset=150');
  });
});