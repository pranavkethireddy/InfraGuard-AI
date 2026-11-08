import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
const h = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('@/api/client', async (orig) => { const m = await orig<typeof import('@/api/client')>(); return { ...m, api: m.createLiveClient('/api/v1', (...a) => h.fetch(...a)) }; });
import { ChaosControl } from '@/components/ChaosControl';
import { FleetPage } from '@/pages/FleetPage';
import { createLiveClient } from '@/api/client';
import { fleetFixtures as f } from '@/api/fleet-fixtures';
import type { ChaosStatus } from '@/api/fleet-types';
const initial: ChaosStatus = { enabled: true, protected_technicians: ['returned-tech/03'], active_faults: ['returned-fault/99'] };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
function mount(node = <ChaosControl />) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return { qc, view: render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>) };
}
const posts = () => h.fetch.mock.calls.filter(([, init]) => init?.method === 'POST');
beforeEach(() => { h.fetch.mockReset(); });

it('GETs authoritative state on mount/open/rerender without sending POST', async () => {
  h.fetch.mockImplementation(async () => json(initial));
  const { view } = mount();
  await waitFor(() => expect(screen.getByRole('switch', { hidden: true })).toHaveAttribute('aria-checked', 'true'));
  expect(h.fetch.mock.calls[0]?.[0]).toBe('/api/v1/fleet/chaos');
  fireEvent.click(screen.getByText('Operator controls'));
  expect(screen.getByText('returned-tech/03')).toBeVisible(); expect(screen.getByText('returned-fault/99')).toBeVisible();
  view.rerender(<QueryClientProvider client={new QueryClient()}><ChaosControl /></QueryClientProvider>);
  expect(posts()).toHaveLength(0);
});
it.each([true, false])('sends exactly enabled=%s only on explicit toggle and renders POST-returned state', async (enabled) => {
  let state = { ...initial, enabled: !enabled };
  h.fetch.mockImplementation(async (_url: string, init?: RequestInit) => { if (init?.method === 'POST') state = { enabled, protected_technicians: ['post-tech'], active_faults: ['post-fault'] }; return json(state); });
  const { qc } = mount(); const invalidate = vi.spyOn(qc, 'invalidateQueries');
  fireEvent.click(screen.getByText('Operator controls'));
  await waitFor(() => expect(screen.getByRole('switch')).toBeEnabled());
  fireEvent.click(screen.getByRole('switch'));
  await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', String(enabled)));
  expect(posts()).toHaveLength(1); expect(posts()[0]?.[0]).toBe('/api/v1/fleet/chaos');
  expect(JSON.parse(posts()[0]?.[1].body)).toEqual({ enabled });
  expect(posts()[0]?.[1].headers['Content-Type']).toBe('application/json');
  expect(screen.getByText('post-tech')).toBeVisible(); expect(screen.getByText('post-fault')).toBeVisible();
  for (const key of ['fleet', 'incident', 'incidents', 'ops']) expect(invalidate).toHaveBeenCalledWith({ queryKey: [key] });
});
it('blocks pending/duplicate clicks and never displays an optimistic state', async () => {
  let finish: ((value: Response) => void) | undefined;
  h.fetch.mockImplementation((_url: string, init?: RequestInit) => init?.method === 'POST' ? new Promise<Response>((r) => { finish = r; }) : Promise.resolve(json(initial)));
  mount(); fireEvent.click(screen.getByText('Operator controls'));
  await waitFor(() => expect(screen.getByRole('switch')).toBeEnabled());
  fireEvent.click(screen.getByRole('switch')); fireEvent.click(screen.getByRole('switch'));
  await waitFor(() => expect(posts()).toHaveLength(1));
  expect(screen.getByRole('switch')).toBeDisabled(); expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true');
  expect(screen.getByText('Chaos change pending…')).toBeVisible();
  await act(async () => { finish?.(json(initial)); });
  await waitFor(() => expect(screen.getByRole('switch')).toBeEnabled());
  expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true');
});
it('blocks the toggle while initial GET is loading', () => {
  h.fetch.mockImplementation(() => new Promise(() => {})); mount(); fireEvent.click(screen.getByText('Operator controls'));
  expect(screen.getByRole('switch')).toBeDisabled(); expect(screen.getByText('Loading chaos status…')).toBeVisible();
  fireEvent.click(screen.getByRole('switch')); expect(posts()).toHaveLength(0);
});
it('shows GET failure/request ID and retries only the read', async () => {
  h.fetch.mockImplementation(async () => json({ error: { message: 'Chaos read unavailable', code: 'CHAOS_READ_FAILED', request_id: 'get-chaos-rid' } }, 503));
  mount(); fireEvent.click(screen.getByText('Operator controls'));
  expect(await screen.findByText(/get-chaos-rid/)).toBeVisible(); expect(screen.getByRole('switch')).toBeDisabled();
  h.fetch.mockImplementation(async () => json(initial)); fireEvent.click(screen.getByRole('button', { name: 'Retry chaos status' }));
  await waitFor(() => expect(screen.getByRole('switch')).toBeEnabled()); expect(posts()).toHaveLength(0);
});
it('shows POST failure/request ID without changing returned state or automatic retry', async () => {
  h.fetch.mockImplementation(async (_url: string, init?: RequestInit) => json(init?.method === 'POST' ? { error: { message: 'Change rejected', code: 'CHAOS_REJECTED', request_id: 'post-chaos-rid' } } : initial, init?.method === 'POST' ? 422 : 200));
  mount(); fireEvent.click(screen.getByText('Operator controls')); await waitFor(() => expect(screen.getByRole('switch')).toBeEnabled());
  fireEvent.click(screen.getByRole('switch')); expect(await screen.findByText(/post-chaos-rid/)).toBeVisible();
  await waitFor(() => expect(screen.getByRole('switch')).toBeEnabled()); expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true');
  expect(posts()).toHaveLength(1);
});
it('polls returned state and IDs regularly without mutation', async () => {
  let state = initial; h.fetch.mockImplementation(async () => json(state));
  mount(); fireEvent.click(screen.getByText('Operator controls')); await screen.findByText('returned-tech/03');
  state = { enabled: false, protected_technicians: [], active_faults: ['polled-fault'] };
  expect(await screen.findByText('polled-fault', {}, { timeout: 2500 })).toBeVisible();
  expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false'); expect(screen.queryByText('returned-tech/03')).not.toBeInTheDocument();
  expect(posts()).toHaveLength(0);
});
it('includes the control on Live fleet without making an automatic fleet mutation', async () => {
  h.fetch.mockImplementation(async (url: string) => json(url.endsWith('/chaos') ? initial : url.includes('/sites') ? f.sites : url.includes('/status') ? f.status : f.map));
  mount(<FleetPage site="datacenter" onSiteChange={vi.fn()} />); fireEvent.click(screen.getByText('Operator controls'));
  await waitFor(() => expect(screen.getByRole('switch')).toBeEnabled()); expect(posts()).toHaveLength(0);
});
it('supports absolute API overrides for exact GET and POST paths', async () => {
  const fetcher = vi.fn(async () => json(initial)); const client = createLiveClient('https://api.example.test/api/v1/', fetcher);
  expect(await client.fleetChaos()).toEqual(initial); expect(await client.setFleetChaos({ enabled: false })).toEqual(initial);
  expect(fetcher.mock.calls.map((call) => (call as unknown[])[0])).toEqual(['https://api.example.test/api/v1/fleet/chaos', 'https://api.example.test/api/v1/fleet/chaos']);
});