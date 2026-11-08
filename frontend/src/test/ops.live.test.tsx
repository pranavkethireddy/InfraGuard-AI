import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
const h = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('@/api/client', async (orig) => {
  const m = await orig<typeof import('@/api/client')>();
  return { ...m, DATA_MODE: 'live', api: m.createLiveClient('http://t/api/v1', (...a) => h.fetch(...a)) };
});
import { createFixtureClient, createLiveClient } from '@/api/client';
import { opsFixtures as f, type JsonShape } from '@/api/ops-fixtures';
import type { DispatchRequest, DispatchResponse, WhatIfResponse } from '@/api/ops-types';
import dispatchRequest from '@/api/fixtures/contracts/ops.dispatch.request.json';
import dispatchResponse from '@/api/fixtures/contracts/ops.dispatch.response.json';
import { learningCasesQuery, planQuery, techniciansQuery, whatIfQuery } from '@/api/ops-queries';
import { DispatchControl, IncidentWhatIf, WhatIfCurves } from '@/components/OperationsWorkspace';
import { OperationsPage } from '@/pages/OperationsPage';
const checkedRequest: JsonShape<DispatchRequest> = dispatchRequest;
const checkedResponse: JsonShape<DispatchResponse> = dispatchResponse;
void checkedRequest; void checkedResponse;
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
function mount(child: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrap = (c: React.ReactNode) => <QueryClientProvider client={qc}>{c}</QueryClientProvider>;
  return { qc, wrap, view: render(wrap(child)) };
}
beforeEach(() => {
  h.fetch.mockReset();
  h.fetch.mockImplementation(async (url: string, init?: RequestInit) => {
    if (init?.method === 'POST') return json(dispatchResponse, 201);
    const u = new URL(url); const mining = u.searchParams.get('site') === 'mining';
    if (u.pathname.endsWith('/whatif')) return json(f.whatif);
    if (u.pathname.endsWith('/technicians')) return json(mining ? { ...f.technicians, technicians: [], work_orders: [] } : f.technicians);
    if (u.pathname.endsWith('/plan')) return json(mining ? { ...f.plan, site_id: 'mining', items: [] } : f.plan);
    if (u.pathname.endsWith('/matrix')) return json(f.matrix);
    if (u.pathname.endsWith('/cases')) return json(mining ? { items: [], total: 0 } : f.cases);
    return json({ error: { code: 'NOT_FOUND', message: 'Not found', request_id: 'r' } }, 404);
  });
});
describe('Merged operations contracts', () => {
  it('keeps the exact fixture costs/recommendation/curve values and disables fixture dispatch', async () => {
    const client = createFixtureClient();
    expect(await client.incidentWhatIf('inc-000955')).toEqual(f.whatif);
    expect(f.whatif.options.map((o) => o.option)).toEqual(['fix_now', 'wait_for_window', 'buy_time']);
    expect(f.whatif.options[0]?.costs.total).toBe(54237.5);
    expect(f.whatif.options[0]?.curve?.[1]).toEqual({ hour: 0.5, value: 44.7, power_state: 'off' });
    await expect(client.incidentWhatIf('inc-demo-001')).rejects.toMatchObject({ status: 404 });
    await expect(client.dispatch({ incident_id: 'inc-000955', option: 'buy_time' })).rejects.toMatchObject({ code: 'fixture_mode' });
    expect(dispatchRequest).toEqual({ incident_id: 'inc-000955', option: 'buy_time' });
    expect(dispatchResponse.work_order.mitigation_active).toBe(true);
  });
  it('keys crew/plan/cases by site and polls open crew/plan/what-if at one second', () => {
    for (const query of [techniciansQuery, planQuery]) {
      expect(query('datacenter').queryKey).not.toEqual(query('mining').queryKey);
      expect(query('mining').refetchInterval).toBe(1000);
    }
    expect(whatIfQuery('a').queryKey).not.toEqual(whatIfQuery('b').queryKey);
    expect(whatIfQuery('a').refetchInterval).toBe(1000);
    expect(learningCasesQuery('mining', 'asic_miner').queryKey).toEqual(['learning', 'mining', 'cases', 'asic_miner']);
  });
  it('uses exact GET filters and the explicit selected option payload', async () => {
    const c = createLiveClient('http://t/api/v1', (...a) => h.fetch(...a));
    await c.opsPlan('mining'); await c.opsTechnicians('datacenter'); await c.learningCases('mining', 'asic_miner');
    await c.dispatch({ incident_id: 'inc-000955', option: 'buy_time' });
    expect(h.fetch.mock.calls.map(([u]) => u)).toEqual(['http://t/api/v1/ops/plan?site=mining', 'http://t/api/v1/ops/technicians?site=datacenter', 'http://t/api/v1/learning/cases?site=mining&asset_type=asic_miner', 'http://t/api/v1/ops/dispatch']);
    expect(JSON.parse(h.fetch.mock.calls[3]?.[1].body)).toEqual(dispatchRequest);
  });
  it('retains null curve values, empty curves and power states without zero inference', () => {
    const data: WhatIfResponse = { ...f.whatif, options: f.whatif.options.map((o, n) => ({ ...o, curve: n === 0 ? [{ hour: 2, value: null, power_state: 'off' }] : [] })) };
    mount(<WhatIfCurves data={data} />);
    expect(screen.getByText(/Curves unavailable/)).toBeInTheDocument();
    expect(screen.getByText('Unavailable')).toBeInTheDocument(); expect(screen.getByText('off')).toBeInTheDocument();
    expect(screen.getAllByText('Curve unavailable.')).toHaveLength(2);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });
  it('keeps all three authoritative curves with exact hour/value/power tables', () => {
    mount(<WhatIfCurves data={f.whatif} />);
    expect(screen.getByRole('img', { name: /temperature_c \(C\), DEMO hours/ })).toBeInTheDocument();
    expect(screen.getAllByRole('table')).toHaveLength(3);
    expect(screen.getAllByText('44.7')).toHaveLength(2);
  });
  it('blocks duplicate dispatch while pending, returns work order and invalidates affected caches', async () => {
    let finish: ((r: Response) => void) | undefined;
    h.fetch.mockImplementation(() => new Promise<Response>((r) => { finish = r; }));
    const { qc } = mount(<DispatchControl incidentId="inc-000955" option="buy_time" />);
    for (const key of ['incident', 'incidents', 'assets', 'fleet', 'whatif', 'ops', 'learning']) qc.setQueryData([key, 'test'], 'existing');
    fireEvent.click(screen.getByRole('button', { name: 'Dispatch' }));
    expect(await screen.findByRole('button', { name: 'Dispatching…' })).toBeDisabled();
    expect(screen.getByRole('button')).toHaveAttribute('aria-busy', 'true');
    fireEvent.click(screen.getByRole('button')); expect(h.fetch).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(finish).toBeDefined()); finish?.(json(dispatchResponse, 201));
    expect(await screen.findByText('Dispatched · wo-0006')).toBeInTheDocument();
    expect(screen.getByText('190 DEMO minutes')).toBeInTheDocument();
    expect(screen.getByRole('button')).toBeDisabled();
    for (const key of ['incident', 'incidents', 'assets', 'fleet', 'whatif', 'ops', 'learning']) expect(qc.getQueryState([key, 'test'])?.isInvalidated).toBe(true);
  });
  it.each(['ALREADY_DISPATCHED', 'INCIDENT_RESOLVED', 'TECHNICIAN_BUSY', 'NO_TECHNICIAN', 'TECHNICIAN_NOT_QUALIFIED', 'OPTION_NOT_AVAILABLE'])('refreshes on %s, preserves context and request ID, requires manual retry', async (code) => {
    const status = code.includes('QUALIFIED') || code.includes('OPTION') ? 422 : 409;
    h.fetch.mockResolvedValue(json({ error: { code, message: 'Review changed state', request_id: 'ops-req-42' } }, status));
    const { qc } = mount(<><p>Existing evidence</p><DispatchControl incidentId="inc-000955" option="fix_now" /></>);
    qc.setQueryData(['ops', 'datacenter', 'plan'], f.plan);
    fireEvent.click(screen.getByRole('button', { name: 'Dispatch' }));
    expect(await screen.findByText(/ops-req-42/)).toBeInTheDocument(); expect(screen.getByText('Existing evidence')).toBeInTheDocument();
    expect(qc.getQueryState(['ops', 'datacenter', 'plan'])?.isInvalidated).toBe(true);
    expect(h.fetch).toHaveBeenCalledTimes(1);
    if (code === 'ALREADY_DISPATCHED' || code === 'INCIDENT_RESOLVED') expect(screen.getByRole('button', { name: 'Dispatch unavailable' })).toBeDisabled();
    else expect(screen.getByRole('button', { name: 'Retry dispatch' })).toBeEnabled();
  });
  it('blocks resolved and already-dispatched incidents without a POST', async () => {
    mount(<IncidentWhatIf id="inc-000955" resolved workOrderId="wo-6" />);
    await screen.findByText('Resolved — dispatch unavailable.');
    expect(screen.queryByText('Already dispatched — active work order.')).not.toBeInTheDocument();
    for (const b of screen.getAllByRole('button', { name: 'Dispatch' })) expect(b).toBeDisabled();
    expect(h.fetch.mock.calls.filter(([, i]) => i?.method === 'POST')).toHaveLength(0);
  });
  it('includes technician_id only after explicit selection and retains risk notes', async () => {
    h.fetch.mockImplementation(async (u: string, init?: RequestInit) => init?.method === 'POST' ? json(dispatchResponse, 201) : u.includes('whatif') ? json({ ...f.whatif, options: f.whatif.options.map((o) => ({ ...o, curve: [], risk_note: '30-day risk is not a failure time.' })) }) : json({ ...f.technicians, work_orders: [] }));
    mount(<IncidentWhatIf id="inc-000955" resolved={false} />);
    await screen.findByLabelText('Technician (optional explicit choice)');
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Dispatch' })[0]).toBeEnabled());
    expect(screen.getAllByText('30-day risk is not a failure time.')).toHaveLength(3);
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'tech-01' } });
    fireEvent.click(screen.getAllByRole('button', { name: 'Dispatch' })[0] as HTMLElement);
    await screen.findByText('Dispatched · wo-0006');
    const post = h.fetch.mock.calls.find(([, i]) => i?.method === 'POST');
    expect(JSON.parse(post?.[1].body)).toEqual({ incident_id: 'inc-000955', option: 'fix_now', technician_id: 'tech-01' });
  });
  it('polls actual crew/plan requests and isolates mining with honest empty learning', async () => {
    const change = vi.fn(); const { view, wrap } = mount(<OperationsPage site="datacenter" onSiteChange={change} />);
    await screen.findByText('Maya Ortiz');
    expect(h.fetch.mock.calls.filter(([, i]) => i?.method === 'POST')).toHaveLength(0);
    await waitFor(() => expect(h.fetch.mock.calls.filter(([u]) => String(u).endsWith('/ops/plan?site=datacenter')).length).toBeGreaterThan(1), { timeout: 2200 });
    fireEvent.click(screen.getByRole('tab', { name: 'Crypto mining site' })); expect(change).toHaveBeenCalledWith('mining');
    view.rerender(wrap(<OperationsPage site="mining" onSiteChange={change} />));
    await screen.findByText('No learned cases for this site and asset type.');
    expect(screen.queryByText('Maya Ortiz')).not.toBeInTheDocument();
    expect(screen.getByText('No repair plan items.')).toBeInTheDocument();
    expect(h.fetch.mock.calls.some(([u]) => String(u).endsWith('/ops/technicians?site=mining'))).toBe(true);
  });
  it('renders empty matrix without invented averages', async () => {
    h.fetch.mockImplementation(async (u: string) => json(u.includes('technicians') ? { ...f.technicians, technicians: [] } : u.includes('/plan') ? { ...f.plan, items: [] } : u.includes('/matrix') ? { total_cases: 0, rows: [] } : { items: [], total: 0 }));
    mount(<OperationsPage site="datacenter" onSiteChange={() => {}} />);
    await screen.findByText('No learned cases. No outcomes or averages available.');
    expect(screen.queryByText('1490.83 USD')).not.toBeInTheDocument();
  });
});