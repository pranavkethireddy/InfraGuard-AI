import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, it, vi } from 'vitest';
const h = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('@/api/client', async (orig) => {
  const m = await orig<typeof import('@/api/client')>();
  return { ...m, DATA_MODE: 'live', api: m.createLiveClient('http://t/api/v1', (...a) => h.fetch(...a)) };
});
import { IncidentDetailPage } from '@/pages/IncidentDetailPage';
import { fixtures } from '@/api/fixtures';
import { opsFixtures as f } from '@/api/ops-fixtures';
import dispatch from '@/api/fixtures/contracts/ops.dispatch.response.json';
import { incidentPollInterval } from '@/api/queries';
const json = (v: unknown) => new Response(JSON.stringify(v), { status: 200 });
it('polls assigned unresolved repairs every second and stops only the repair lifecycle on resolution', () => {
  expect(incidentPollInterval({ status: 'acknowledged', work_order_id: 'wo-0006', investigation_status: null })).toBe(1000);
  expect(incidentPollInterval({ status: 'resolved', work_order_id: 'wo-0006', investigation_status: null })).toBe(false);
  expect(incidentPollInterval({ status: 'open', investigation_status: 'queued' })).toBe(1000);
  expect(incidentPollInterval({ status: 'open', investigation_status: 'running' })).toBe(1000);
  expect(incidentPollInterval({ status: 'open', investigation_status: null })).toBe(false);
});
it('refreshes traveling/in_progress to done/resolved on the same incident page and stops repair polling', async () => {
  let stage = 'open'; let incidentCalls = 0; let posts = 0; let learningCalls = 0;
  h.fetch.mockImplementation(async (url: string, init?: RequestInit) => {
    if (init?.method === 'POST') { posts++; stage = 'traveling'; return json(dispatch); }
    if (url.endsWith('/whatif')) return json(f.whatif);
    if (url.includes('/ops/technicians')) return json({ ...f.technicians, work_orders: stage === 'open' ? [] : [{ ...dispatch.work_order, status: stage, progress: stage === 'in_progress' ? 0.5 : stage === 'done' ? 1 : 0, eta_minutes: stage === 'done' ? 0 : 90, completed_at: stage === 'done' ? '2026-11-08T03:00:00Z' : null, cost: stage === 'done' ? { labor: 225, parts: 3500, mitigation: 0, total: 3725 } : null }] });
    if (url.includes('/learning/cases')) { learningCalls++; return json({ items: stage === 'done' ? [{ ...f.cases.items[0], case_id: 'lc-repair', asset_id: 'cooling-02' }] : [], total: stage === 'done' ? 1 : 0 }); }
    if (url.endsWith('/incidents/inc-000955')) { incidentCalls++; return json({ ...fixtures.incidentDetail, incident_id: 'inc-000955', asset_id: 'cooling-02', status: stage === 'done' ? 'resolved' : stage === 'open' ? 'open' : 'acknowledged', resolved_by: stage === 'done' ? 'technician' : null, work_order_id: stage === 'open' ? null : 'wo-0006' }); }
    if (url.includes('/models')) return json(fixtures.modelsList);
    return json(fixtures.assetReadings);
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  qc.setQueryData(['learning', 'matrix'], { total_cases: 0, rows: [] });
  render(<QueryClientProvider client={qc}><IncidentDetailPage id="inc-000955" /></QueryClientProvider>);
  await waitFor(() => expect(screen.getAllByRole('button', { name: 'Dispatch' })[0]).toBeEnabled(), { timeout: 3000 });
  fireEvent.click(screen.getAllByRole('button', { name: 'Dispatch' })[0] as HTMLElement);
  await screen.findByText('Status: acknowledged');
  const current = await screen.findByRole('region', { name: 'Assigned work order' });
  expect(within(current).getByText('traveling', { exact: true })).toBeInTheDocument();
  stage = 'in_progress';
  await within(current).findByText('in_progress', {}, { timeout: 2500 });
  expect(within(current).getByText('0.5', { exact: true })).toBeInTheDocument();
  expect(posts).toBe(1);
  stage = 'done';
  await screen.findByText('Status: resolved', {}, { timeout: 2500 });
  await within(current).findByText('done', {}, { timeout: 2500 });
  expect(within(current).getByText('3725', { exact: true })).toBeInTheDocument();
  expect(screen.queryByText('Already dispatched — active work order.')).not.toBeInTheDocument();
  await screen.findByText('lc-repair', {}, { timeout: 2500 });
  expect(qc.getQueryState(['learning', 'matrix'])?.isInvalidated).toBe(true);
  expect(learningCalls).toBeGreaterThan(0);
  const callsAfterResolution = incidentCalls;
  await new Promise((r) => setTimeout(r, 1200));
  expect(incidentCalls).toBe(callsAfterResolution);
  for (const button of screen.getAllByRole('button', { name: 'Dispatch' })) expect(button).toBeDisabled();
  expect(posts).toBe(1);
}, 10000);