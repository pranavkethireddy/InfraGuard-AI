import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
const h = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('@/api/client', async (orig) => {
  const m = await orig<typeof import('@/api/client')>();
  return { ...m, api: m.createLiveClient('http://t/api/v1', (...args) => h.fetch(...args)) };
});
import { OverviewPage } from '@/pages/OverviewPage';
import { FleetFloor, FleetMachines } from '@/components/FleetWorkspace';
import { fleetFixtures as f } from '@/api/fleet-fixtures';
import type { MachineStatus } from '@/api/fleet-types';

// Test-only additive power examples; approved production fixture bytes are unchanged.
const off: MachineStatus = { ...f.status.machines[0] as MachineStatus, power_state: 'off', power_reason: 'Thermal shutdown', shutdown_eta_minutes: 0,
  work_order: { work_order_id: 'wo-test', technician_id: 'tech-test', technician_name: 'Test technician', status: 'in_progress', option: 'fix_now', progress: 0.4, eta_minutes: 7 } };
const risk: MachineStatus = { ...off, asset_id: 'risk-test', power_state: 'at_risk', power_reason: 'Projected shutdown', shutdown_eta_minutes: 12, work_order: null };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
beforeEach(() => {
  h.fetch.mockReset();
  h.fetch.mockImplementation(async (url: string) => {
    const u = new URL(url);
    if (u.pathname.endsWith('/fleet/map')) return json(u.searchParams.get('site') === 'mining' ? { ...f.map, site_id: 'mining', halls: [] } : f.map);
    if (u.pathname.endsWith('/fleet/status')) return json(u.searchParams.get('site') === 'mining' ? f.mining : f.status);
    if (u.pathname.includes('/fleet/racks/')) return json(f.rack);
    return json({ error: { code: 'NOT_FOUND', message: 'Missing', request_id: 'overview-test' } }, 404);
  });
});
function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return { qc, wrap: (node: React.ReactNode) => <QueryClientProvider client={qc}>{node}</QueryClientProvider> };
}
it('loads the default datacenter map without mutations and opens rack details by click/keyboard', async () => {
  const { wrap } = setup(); render(wrap(<OverviewPage />));
  expect(await screen.findByRole('group', { name: 'Hall A floor map' })).toBeInTheDocument();
  const rack = screen.getByRole('button', { name: /Rack A1-03: critical/ });
  fireEvent.keyDown(rack, { key: 'Enter' });
  expect(await screen.findByRole('region', { name: 'Rack investigation · A1-03' })).toBeInTheDocument();
  await waitFor(() => expect(h.fetch.mock.calls.some(([u]) => String(u).includes('/fleet/racks/A1-03'))).toBe(true));
  fireEvent.click(screen.getByRole('button', { name: 'Close rack details' }));
  fireEvent.click(rack);
  expect(screen.getByRole('region', { name: 'Rack investigation · A1-03' })).toBeInTheDocument();
  expect(h.fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0);
});
it('changes site callbacks and isolates map/status/rack selection and caches', async () => {
  const { wrap, qc } = setup(); const change = vi.fn();
  const view = render(wrap(<OverviewPage site="datacenter" onSiteChange={change} />));
  fireEvent.click(await screen.findByRole('button', { name: /Rack A1-03: critical/ }));
  fireEvent.click(screen.getByRole('tab', { name: 'Crypto mining site' }));
  expect(change).toHaveBeenCalledWith('mining');
  view.rerender(wrap(<OverviewPage site="mining" onSiteChange={change} />));
  expect(await screen.findByText('No facility map returned.')).toBeInTheDocument();
  expect(screen.queryByRole('region', { name: 'Rack investigation · A1-03' })).not.toBeInTheDocument();
  expect(qc.getQueryData(['fleet', 'datacenter', 'map', 30])).toEqual(f.map);
  expect(qc.getQueryData(['fleet', 'mining', 'map', 30])).toMatchObject({ site_id: 'mining', halls: [] });
});
it('does not call no-data health all good or infer missing power from critical health', async () => {
  // Test-only legacy response: omit optional power fields now present in approved fixtures.
  const legacyMap = { ...f.map, halls: f.map.halls.map((hall) => ({ ...hall, racks: hall.racks.map((rack) => {
    const { power_state, shutdown_eta_minutes, ...legacyRack } = rack;
    void [power_state, shutdown_eta_minutes];
    return legacyRack;
  }) })) };
  h.fetch.mockImplementation(async (url: string) => json(String(url).includes('/fleet/map') ? legacyMap : { ...f.status, summary: { ...f.status.summary, no_data: 42 }, machines: [] }));
  const { wrap } = setup(); render(wrap(<OverviewPage />));
  expect(await screen.findByText('No data for some or all machines. Facility health is not fully known.')).toBeInTheDocument();
  const r = await screen.findByRole('button', { name: /Rack A1-03: critical/ });
  expect(r).toHaveAccessibleName('Rack A1-03: critical · Power: Not reported');
  expect(screen.queryByText(/all good/i)).not.toBeInTheDocument();
});
it('renders only returned power, reason, ETA and work-order values separately from health', () => {
  render(<FleetMachines machines={[off, risk]} />);
  expect(screen.getByText('Power: off')).toBeInTheDocument();
  expect(screen.getByText('Power: at_risk')).toBeInTheDocument();
  expect(screen.getByText('Thermal shutdown')).toBeInTheDocument();
  expect(screen.getByText('Projected shutdown')).toBeInTheDocument();
  expect(screen.getByText('12')).toBeInTheDocument();
  expect(screen.getByText('0.4')).toBeInTheDocument();
  expect(screen.getByText('ETA: 7 DEMO minutes')).toBeInTheDocument();
  expect(screen.getByText('Test technician · tech-test')).toBeInTheDocument();
});
it('marks rack off and machine at-risk using explicit returned states and shutdown ETA', () => {
  const hall = f.map.halls[0];
  if (!hall || !hall.racks[0]) throw new Error('Missing approved hall');
  const rack = { ...hall.racks[0], power_state: 'off' as const, shutdown_eta_minutes: 0 };
  render(<FleetFloor halls={[{ ...hall, racks: [rack], machines: [{ ...risk, placement: { ...risk.placement, rack_id: rack.rack_id } }] }]} gridUnit="cells" selected={null} onSelect={() => {}} />);
  expect(screen.getByRole('button', { name: /Power: off.*shutdown ETA 0 DEMO minutes/ })).toHaveClass('stroke-destructive');
  expect(screen.getByRole('img', { name: /Power: at_risk.*shutdown ETA 12 DEMO minutes/ })).toBeInTheDocument();
});
it('shows loading then backend failure and request ID without a fixture fallback', async () => {
  let release: ((r: Response) => void) | undefined;
  h.fetch.mockImplementation(() => new Promise<Response>((resolve) => { release = resolve; }));
  const { wrap } = setup(); render(wrap(<OverviewPage />));
  expect(screen.getByText('Loading facility map…')).toBeInTheDocument();
  release?.(json({ error: { code: 'UNAVAILABLE', message: 'Backend offline', request_id: 'req-power-503' } }, 503));
  expect((await screen.findAllByText('Backend offline')).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/req-power-503/).length).toBeGreaterThan(0);
  expect(screen.queryByRole('group', { name: 'Hall A floor map' })).not.toBeInTheDocument();
});