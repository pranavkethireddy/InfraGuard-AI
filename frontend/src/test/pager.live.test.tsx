import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
const h = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('@/api/client', async (orig) => { const m = await orig<typeof import('@/api/client')>(); return { ...m, DATA_MODE: 'live', API_BASE_URL: 'http://t/api/v1', api: m.createLiveClient('http://t/api/v1', (...a) => h.fetch(...a)) }; });
import { createFixtureClient, createLiveClient } from '@/api/client';
import { crewKey, newerPager, opsStreamUrl, pagerKey, useCrewStream } from '@/api/ops-stream';
import { PagerPage } from '@/pages/PagerPage';
import { SiteFloor } from '@/components/SiteFloor';
import { AutoDispatch } from '@/components/AutoDispatch';
import { opsFixtures } from '@/api/ops-fixtures';
import { fleetFixtures } from '@/api/fleet-fixtures';
import { pagerFixtures } from '@/api/pager-fixtures';
import walkingJson from '@/api/fixtures/contracts/ops.pager.walking.response.json';
import claimJson from '@/api/fixtures/contracts/ops.pager.claim.response.json';
import type { PagerView } from '@/api/ops-types';
const paged = pagerFixtures.paged;
const walking = walkingJson as PagerView;
const claim = claimJson as PagerView;
class FakeSource {
  static all: FakeSource[] = [];
  readyState = 0; closed = false; listeners = new Map<string, Set<(e: Event) => void>>();
  constructor(public url: string) { FakeSource.all.push(this); }
  addEventListener(event: string, listener: (e: Event) => void) { const set = this.listeners.get(event) ?? new Set(); set.add(listener); this.listeners.set(event, set); }
  removeEventListener(event: string, listener: (e: Event) => void) { this.listeners.get(event)?.delete(listener); }
  close() { this.closed = true; this.readyState = 2; }
  emit(event: string, data?: unknown) { for (const listener of this.listeners.get(event) ?? []) listener(new MessageEvent(event, { data: typeof data === 'string' ? data : JSON.stringify(data) })); }
}
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
function mount(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrap = (child: React.ReactNode) => <QueryClientProvider client={qc}>{child}</QueryClientProvider>;
  return { qc, wrap, view: render(wrap(node)) };
}
beforeEach(() => { FakeSource.all = []; vi.stubGlobal('EventSource', FakeSource); h.fetch.mockReset(); h.fetch.mockImplementation(async () => response(paged)); });
afterEach(() => vi.unstubAllGlobals());
describe('Approved pager and floor', () => {
  it('preserves approved statuses, request fields and fixture mutation blocking', async () => {
    expect(paged.job?.work_order.status).toBe('paged'); expect(paged.job?.actions).toEqual(['accept', 'decline']);
    expect(walking.job?.work_order.status).toBe('traveling'); expect(claim.technician.device_controlled).toBe(true);
    const fixture = createFixtureClient(); expect(await fixture.opsPager('tech-03')).toEqual(paged);
    for (const action of [fixture.claimPager('tech-03'), fixture.releasePager('tech-03'), fixture.pagerAction('tech-03', { action: 'accept', work_order_id: 'wo-0006' }), fixture.setAutoDispatch(false)]) await expect(action).rejects.toMatchObject({ code: 'fixture_mode' });
  });
  it('uses the same API base and encodes technician and site stream queries', async () => {
    expect(opsStreamUrl({ technician_id: 'tech /?' }, 'http://lan:8000/api/v1')).toBe('http://lan:8000/api/v1/ops/stream?technician_id=tech+%2F%3F');
    const c = createLiveClient('http://t/api/v1', (...args) => h.fetch(...args));
    await c.claimPager('tech /'); await c.releasePager('tech /'); await c.pagerAction('tech /', { action: 'done', work_order_id: 'wo-1' }); await c.opsFloor('mining');
    expect(h.fetch.mock.calls[0]?.[0]).toBe('http://t/api/v1/ops/pager/tech%20%2F/claim');
    expect(h.fetch.mock.calls[0]?.[1].body).toBeUndefined(); expect(h.fetch.mock.calls[1]?.[1].body).toBeUndefined();
    expect(JSON.parse(h.fetch.mock.calls[2]?.[1].body)).toEqual({ action: 'done', work_order_id: 'wo-1' });
    expect(h.fetch.mock.calls[3]?.[0]).toBe('http://t/api/v1/ops/floor?site=mining');
  });
  it('renders one hall translation, global technician dots and exact backend waypoints', () => {
    const technician = walking.technician;
    const select = vi.fn();
    mount(<SiteFloor floor={pagerFixtures.floor} halls={fleetFixtures.map.halls} technicians={[technician]} selected={null} onSelect={select} />);
    const hall = document.querySelector('[data-hall="hall-b"]'); expect(hall?.getAttribute('transform')).toBe('translate(20 0)');
    const dot = document.querySelector('[data-technician="tech-03"]'); expect(dot?.getAttribute('cx')).toBe(String(technician.position?.x)); expect(dot?.getAttribute('cy')).toBe(String(technician.position?.y));
    expect(document.querySelector('[data-technician-path="tech-03"]')?.getAttribute('points')).toBe(technician.path?.map((p) => `${p.x},${p.y}`).join(' '));
    const rack = screen.getAllByRole('button').find((b) => b.tagName.toLowerCase() === 'rect'); if (!rack) throw new Error('Missing rack'); fireEvent.keyDown(rack, { key: 'Enter' }); expect(select).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole('button', { name: /^Sam Rivera: / })); expect(screen.getByRole('region', { name: 'Selected technician' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Open pager/ })).toHaveAttribute('href', '/pager?technician=tech-03');
  });
  it('retains a keyboard text fallback when positions are unavailable', () => {
    mount(<SiteFloor floor={pagerFixtures.floor} halls={[]} technicians={[{ ...paged.technician, position: null, path: [] }]} selected={null} onSelect={vi.fn()} />);
    expect(screen.getByText(/Coordinates unavailable/)).toBeInTheDocument(); expect(screen.getByRole('button', { name: 'Sam Rivera · idle' })).toBeInTheDocument();
  });
  it('guards older snapshots monotonically across initial GET, stream and POST', async () => {
    let finish: ((r: Response) => void) | undefined;
    h.fetch.mockImplementation(() => new Promise<Response>((r) => { finish = r; }));
    const { qc } = mount(<PagerPage onTechnicianChange={vi.fn()} />);
    await waitFor(() => expect(FakeSource.all).toHaveLength(1));
    const source = FakeSource.all[0]; if (!source) throw new Error('Missing source');
    act(() => source.emit('pager', { ...walking, version: 20 }));
    await waitFor(() => expect(screen.getAllByText('traveling', { selector: 'span' }).length).toBeGreaterThan(0));
    await act(async () => finish?.(response({ ...paged, version: 6 })));
    expect(qc.getQueryData<PagerView>(pagerKey('tech-03'))?.version).toBe(20);
    act(() => source.emit('pager', paged)); expect(qc.getQueryData<PagerView>(pagerKey('tech-03'))?.version).toBe(20);
    expect(newerPager({ ...walking, version: 20 }, paged).version).toBe(20);
  });
  it('handles reconnect, malformed events and cleanup on technician switch without losing good data', async () => {
    const { view, wrap } = mount(<PagerPage onTechnicianChange={vi.fn()} />);
    await screen.findByRole('button', { name: 'Accept job' });
    const source = FakeSource.all[0]; if (!source) throw new Error('Missing source');
    act(() => { source.readyState = 1; source.emit('open'); }); expect(screen.getByText('Stream: live')).toBeInTheDocument();
    act(() => { source.readyState = 0; source.emit('error'); }); expect(screen.getByText('Stream: reconnecting')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Accept job' })).toBeInTheDocument();
    act(() => source.emit('pager', 'bad-json')); expect(screen.getByText(/Malformed stream event/)).toBeInTheDocument();
    act(() => source.emit('pager', { ...walking, version: 20 })); expect(screen.getByText('Stream: live')).toBeInTheDocument();
    view.rerender(wrap(<PagerPage technicianId="tech-04" onTechnicianChange={vi.fn()} />));
    await waitFor(() => expect(source.closed).toBe(true)); expect(source.listeners.get('pager')?.size).toBe(0);
    view.unmount(); expect(FakeSource.all.every((s) => s.closed)).toBe(true);
  });
  it('runs paged -> accept -> travel -> awaiting_confirmation -> done on the same page, blocking duplicates', async () => {
    let finish: ((r: Response) => void) | undefined;
    h.fetch.mockImplementation(async (_url: string, init?: RequestInit) => init?.method === 'POST' ? new Promise<Response>((r) => { finish = r; }) : response(paged));
    const { qc, view } = mount(<PagerPage onTechnicianChange={vi.fn()} />);
    const accept = await screen.findByRole('button', { name: 'Accept job' }); expect(h.fetch.mock.calls.filter(([, i]) => i?.method === 'POST')).toHaveLength(0);
    fireEvent.click(accept); fireEvent.click(accept); await waitFor(() => expect(accept).toBeDisabled()); expect(h.fetch.mock.calls.filter(([, i]) => i?.method === 'POST')).toHaveLength(1);
    await act(async () => finish?.(response({ ...walking, version: 10 })));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Accept job' })).not.toBeInTheDocument()); expect(screen.queryByRole('button', { name: 'Arrived' })).not.toBeInTheDocument();
    const source = FakeSource.all[0]; if (!source || !walking.job) throw new Error('Missing data');
    const waiting: PagerView = { ...walking, version: 11, job: { ...walking.job, work_order: { ...walking.job.work_order, status: 'awaiting_confirmation' }, actions: ['done'] } };
    act(() => source.emit('pager', waiting)); const done = await screen.findByRole('button', { name: 'Done' });
    fireEvent.click(done); await waitFor(() => expect(h.fetch.mock.calls.filter(([, i]) => i?.method === 'POST')).toHaveLength(2));
    const completed: PagerView = { ...waiting, version: 12, job: { ...waiting.job, ...(waiting.job ?? walking.job), work_order: { ...walking.job.work_order, status: 'done', cost: { labor: 75, parts: 10, mitigation: 0, total: 85 } }, actions: [] } };
    await act(async () => finish?.(response(completed)));
    await waitFor(() => expect(screen.getByText('done', { selector: 'span' })).toBeInTheDocument()); expect(screen.queryByRole('button', { name: 'Done' })).not.toBeInTheDocument(); expect(qc.getQueryData<PagerView>(pagerKey('tech-03'))?.version).toBe(12);
    view.unmount(); expect(h.fetch.mock.calls.filter(([, i]) => i?.method === 'POST')).toHaveLength(2);
  });
  it('claims and releases only on explicit input and refetches stale 409 actions with request IDs', async () => {
    const uncontrolled = { ...paged, technician: { ...paged.technician, device_controlled: false }, version: 1 };
    h.fetch.mockImplementation(async (url: string, init?: RequestInit) => init?.method !== 'POST' ? response(uncontrolled) : url.endsWith('/claim') ? response({ ...paged, version: 10 }) : url.endsWith('/release') ? response({ ...uncontrolled, version: 20 }) : response({ error: { code: 'NOT_PAGED', message: 'Job changed', request_id: 'pager-rid' } }, 409));
    mount(<PagerPage onTechnicianChange={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Take control' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Release control' }));
    await screen.findByRole('button', { name: 'Take control' });
    fireEvent.click(screen.getByRole('button', { name: 'Accept job' })); await screen.findByText(/pager-rid/);
    expect(h.fetch.mock.calls.filter(([u, i]) => u.endsWith('/tech-03') && i?.method !== 'POST').length).toBeGreaterThan(1);
  });
  it('keeps crew streams site-isolated and does not continuously poll', async () => {
    h.fetch.mockImplementation(async (url: string) => response({ ...opsFixtures.technicians, technicians: url.includes('mining') ? [] : opsFixtures.technicians.technicians }));
    function Crew({ site }: { site: 'datacenter' | 'mining' }) { const q = useCrewStream(site); return <p>{q.data?.demo_time}</p>; }
    const { qc, view, wrap } = mount(<Crew site="datacenter" />); await waitFor(() => expect(qc.getQueryData(crewKey('datacenter'))).toBeDefined());
    const source = FakeSource.all[0]; if (!source) throw new Error('No source');
    act(() => source.emit('crew', { ...opsFixtures.technicians, technicians: opsFixtures.technicians.technicians.filter((t) => t.site_id === 'datacenter'), work_orders: opsFixtures.technicians.work_orders.filter((w) => w.site_id === 'datacenter'), demo_time: 'new-time' })); expect(screen.getByText('new-time')).toBeInTheDocument();
    view.rerender(wrap(<Crew site="mining" />)); await waitFor(() => expect(source.closed).toBe(true));
    expect(FakeSource.all[1]?.url).toBe('http://t/api/v1/ops/stream?site=mining');
    expect(qc.getQueryData(crewKey('mining'))).not.toEqual(qc.getQueryData(crewKey('datacenter')));
  });
  it('changes automatic dispatch only explicitly and displays the returned state', async () => {
    h.fetch.mockImplementation(async () => response({ enabled: false }));
    const { qc } = mount(<AutoDispatch enabled />); qc.setQueryData(crewKey('datacenter'), opsFixtures.technicians);
    expect(h.fetch).not.toHaveBeenCalled(); fireEvent.click(screen.getByRole('switch', { name: 'Automatic dispatch' }));
    await waitFor(() => expect(qc.getQueryData<{ auto_dispatch: boolean }>(crewKey('datacenter'))?.auto_dispatch).toBe(false));
    expect(JSON.parse(h.fetch.mock.calls[0]?.[1].body)).toEqual({ enabled: false });
  });
  it('retains a newer SSE when an older mutation completes', async () => {
    let finish: ((r: Response) => void) | undefined;
    h.fetch.mockImplementation(async (_url: string, init?: RequestInit) => init?.method === 'POST' ? new Promise<Response>((r) => { finish = r; }) : response(paged));
    const { qc } = mount(<PagerPage onTechnicianChange={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Accept job' }));
    await waitFor(() => expect(finish).toBeDefined());
    const source = FakeSource.all[0]; if (!source) throw new Error('No source');
    act(() => source.emit('pager', { ...walking, version: 40 }));
    await act(async () => finish?.(response({ ...paged, version: 10 })));
    await waitFor(() => expect(qc.getQueryData<PagerView>(pagerKey('tech-03'))?.version).toBe(40));
    expect(screen.queryByRole('button', { name: 'Accept job' })).not.toBeInTheDocument();
  });
  it('does not poll streamed crew, and marks disconnected last-good data stale', async () => {
    h.fetch.mockImplementation(async () => response(opsFixtures.technicians));
    function Crew() { const q = useCrewStream('datacenter'); return <p>{q.stream.state}</p>; }
    const { view } = mount(<Crew />); await waitFor(() => expect(h.fetch).toHaveBeenCalledOnce());
    const source = FakeSource.all[0]; if (!source) throw new Error('No source');
    vi.useFakeTimers({ toFake: ['Date'] });
    act(() => { source.readyState = 1; source.emit('crew', { ...opsFixtures.technicians, technicians: [], work_orders: [] }); });
    act(() => vi.setSystemTime(Date.now() + 12000)); expect(h.fetch).toHaveBeenCalledOnce(); expect(screen.getByText('live')).toBeInTheDocument();
    act(() => { source.readyState = 0; source.emit('error'); vi.setSystemTime(Date.now() + 12000); }); await waitFor(() => expect(screen.getByText('stale')).toBeInTheDocument(), { timeout: 2000 });
    view.unmount(); vi.useRealTimers();
  });
});