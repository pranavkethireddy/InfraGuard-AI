import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
const h = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('@/api/client', async (orig) => { const m = await orig<typeof import('@/api/client')>(); return { ...m, api: m.createLiveClient('/api/v1', (...a) => h.fetch(...a)) }; });
import { EquipmentFaultControl } from '@/components/EquipmentFaultControl';
import { EquipmentPage } from '@/pages/EquipmentPage';
import { RackPage } from '@/pages/RackPage';
import { facilityFixtures as f } from '@/api/facility-fixtures';
import { facilityFaults } from '@/api/facility-spec';
import { createLiveClient } from '@/api/client';
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const posts = () => h.fetch.mock.calls.filter(([, init]) => init?.method === 'POST');
function mount(child: React.ReactNode) { const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } }); return { qc, ...render(<QueryClientProvider client={qc}>{child}</QueryClientProvider>) }; }
beforeEach(() => { h.fetch.mockReset(); h.fetch.mockImplementation(async () => json({ injected: [], live: f.map.live })); });
it.each(Object.entries(facilityFaults).flatMap(([type, kinds]) => kinds.map((kind) => [type, kind] as const)))('posts only explicit compatible %s/%s with exact returned ID', async (type, kind) => {
  const machine = f.status.machines.find((m) => m.asset_type === type); if (!machine) throw new Error('Missing fixture family');
  mount(<EquipmentFaultControl machines={f.status.machines} />);
  fireEvent.click(screen.getByText('Facility fault controls', { selector: 'summary' }));
  fireEvent.change(screen.getByLabelText('Facility equipment'), { target: { value: machine.asset_id } });
  fireEvent.change(screen.getByLabelText('Facility fault choice'), { target: { value: kind } });
  expect(posts()).toHaveLength(0);
  fireEvent.click(screen.getByRole('button', { name: 'Inject equipment fault' }));
  await screen.findByText('Equipment fault request completed.');
  expect(posts()).toHaveLength(1); expect(posts()[0]?.[0]).toBe('/api/v1/fleet/faults'); expect(JSON.parse(posts()[0]?.[1].body)).toEqual({ asset_ids: [machine.asset_id], kind });
});
it('locks pending duplicate clicks, preserves 422 request ID and permits explicit retry', async () => {
  let finish: ((r: Response) => void) | undefined; h.fetch.mockImplementation(() => new Promise<Response>((r) => { finish = r; }));
  mount(<EquipmentFaultControl machines={f.status.machines} />);
  fireEvent.click(screen.getByText('Facility fault controls', { selector: 'summary' })); fireEvent.change(screen.getByLabelText('Facility equipment'), { target: { value: 'ups-01' } });
  const button = screen.getByRole('button', { name: 'Inject equipment fault' }); fireEvent.click(button); fireEvent.click(button);
  await waitFor(() => expect(posts()).toHaveLength(1)); expect(screen.getByLabelText('Facility equipment')).toBeDisabled();
  await act(async () => finish?.(json({ error: { code: 'FAULT_KIND_NOT_SUPPORTED', message: 'Rejected family', request_id: 'facility-422' } }, 422)));
  expect(await screen.findByText(/facility-422/)).toBeInTheDocument(); expect(screen.getByText('Rejected family')).toBeInTheDocument();
  h.fetch.mockImplementation(async () => json({ injected: [], live: f.map.live })); fireEvent.click(screen.getByRole('button', { name: 'Inject equipment fault' })); await screen.findByText('Equipment fault request completed.'); expect(posts()).toHaveLength(2);
});
it('does not mutate while loading, errored, empty, mounting or rerendering', () => {
  const v = mount(<EquipmentFaultControl machines={[]} loading />); expect(screen.getByRole('button', { name: 'Inject equipment fault', hidden: true })).toBeDisabled();
  v.rerender(<QueryClientProvider client={v.qc}><EquipmentFaultControl machines={[]} error={new Error('No inventory')} /></QueryClientProvider>);
  fireEvent.click(screen.getByText('Facility fault controls', { selector: 'summary' })); expect(screen.getByText('No inventory')).toBeInTheDocument(); expect(posts()).toHaveLength(0);
});
it('refreshes mounted equipment metrics, status, observed time and incident link without altering values', async () => {
  let data = structuredClone(f.status); h.fetch.mockImplementation(async () => json(data));
  const { qc } = mount(<EquipmentPage id="ups-01" site="datacenter" />);
  const region = await screen.findByRole('region', { name: 'Equipment details · ups-01' });
  data = { ...data, machines: data.machines.map((m) => m.asset_id === 'ups-01' ? { ...m, status: 'critical', latest_values: { output_kw: 0, load_pct: 99 }, last_reading_at: '2026-11-08T09:01:22Z', active_incident: { incident_id: 'inc /1', title: 'Returned power incident', status: 'open', risk_level: 'high', opened_at: '2026-11-08T09:01:22Z', estimated_total_impact: 123, cost_per_day: 456, investigation_status: null } } : m) };
  await act(async () => { await qc.invalidateQueries({ queryKey: ['fleet', 'datacenter', 'status'] }); });
  await waitFor(() => expect(within(region).getByText('critical')).toBeInTheDocument()); expect(within(region).getByText('99')).toBeInTheDocument(); expect(within(region).getByRole('link', { name: /Returned power incident/ })).toHaveAttribute('href', '/incidents/inc%20%2F1'); expect(region).toHaveTextContent('09:01:22'); expect(posts()).toHaveLength(0);
});
it('refreshes mounted rack PDU/ToR separately, retaining null states', async () => {
  let rack = structuredClone(f.rack); h.fetch.mockImplementation(async () => json(rack));
  const { qc } = mount(<RackPage id="A1-01" />); const region = await screen.findByRole('region', { name: 'Equipment details · pdu-A1-01' });
  if (!rack.pdu) throw new Error('Missing PDU'); rack = { ...rack, pdu: { ...rack.pdu, status: 'warning', latest_values: { power_kw: 0 } }, tor: null };
  await act(async () => { await qc.invalidateQueries({ queryKey: ['fleet'] }); });
  await waitFor(() => expect(within(region).getByText('warning')).toBeInTheDocument()); expect(screen.queryByRole('region', { name: 'Equipment details · tor-A1-01' })).not.toBeInTheDocument(); expect(posts()).toHaveLength(0);
});
it('uses encoded rack paths/history and preserves exact backend error envelopes', async () => {
  const api = createLiveClient('/api/v1', (...a) => h.fetch(...a)); h.fetch.mockImplementation(async () => json({ error: { code: 'RACK_NOT_FOUND', message: 'Missing rack', request_id: 'rack-404' } }, 404));
  await expect(api.fleetRack('rack /?#')).rejects.toMatchObject({ status: 404, code: 'RACK_NOT_FOUND', requestId: 'rack-404' }); expect(h.fetch.mock.calls[0]?.[0]).toBe('/api/v1/fleet/racks/rack%20%2F%3F%23?history=30');
});