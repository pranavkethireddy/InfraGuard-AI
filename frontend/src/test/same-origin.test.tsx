import { render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import { API_BASE_URL, createLiveClient } from '@/api/client';
import { opsStreamUrl, useCrewStream } from '@/api/ops-stream';

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.resetModules(); });

it('defaults fetch to same-origin /api/v1 without a localhost dependency', async () => {
  expect(API_BASE_URL).toBe('/api/v1');
  const fetcher = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({ sites: [] })));
  await createLiveClient(undefined, fetcher).fleetSites();
  expect(fetcher.mock.calls[0]?.[0]).toBe('/api/v1/fleet/sites');
});

it.each(['/api/v1/', 'https://example.org/api/v1/'])('preserves base prefix and encoded paths for %s', async (base) => {
  const fetcher = vi.fn<typeof fetch>(async () => new Response('{}'));
  const client = createLiveClient(base, fetcher);
  await client.getAsset('server /?');
  await client.opsTechnicians('mining');
  expect(fetcher.mock.calls[0]?.[0]).toBe(`${base.slice(0, -1)}/assets/server%20%2F%3F`);
  expect(fetcher.mock.calls[1]?.[0]).toBe(`${base.slice(0, -1)}/ops/technicians?site=mining`);
  expect(opsStreamUrl({ technician_id: 'tech /?' }, base)).toBe(`${base.slice(0, -1)}/ops/stream?technician_id=tech+%2F%3F`);
});

it('honors an explicit absolute environment base for fetch and EventSource', async () => {
  vi.stubEnv('VITE_API_BASE_URL', 'https://public.example/api/v1');
  vi.stubEnv('VITE_DATA_MODE', 'live');
  vi.resetModules();
  const fetcher = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({ technicians: [], work_orders: [], demo_time: 'returned' })));
  const streams: string[] = [];
  class Source {
    readyState = 0;
    constructor(url: string) { streams.push(url); }
    addEventListener() {} removeEventListener() {} close() {}
  }
  vi.stubGlobal('fetch', fetcher); vi.stubGlobal('EventSource', Source);
  const client = await import('@/api/client');
  const stream = await import('@/api/ops-stream');
  function Crew() { stream.useCrewStream('mining'); return null; }
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(<QueryClientProvider client={qc}><Crew /></QueryClientProvider>);
  await waitFor(() => expect(fetcher).toHaveBeenCalledOnce());
  expect(client.API_BASE_URL).toBe('https://public.example/api/v1');
  expect(fetcher.mock.calls[0]?.[0]).toBe('https://public.example/api/v1/ops/technicians?site=mining');
  expect(streams).toEqual(['https://public.example/api/v1/ops/stream?site=mining']);
  view.unmount(); qc.clear();
});

it('opens same-origin crew fetch and EventSource without mutations', async () => {
  vi.stubEnv('VITE_API_BASE_URL', '/api/v1'); vi.stubEnv('VITE_DATA_MODE', 'live'); vi.resetModules();
  const fetcher = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({ technicians: [], work_orders: [], demo_time: 'returned' })));
  const streams: string[] = [];
  class Source {
    readyState = 0;
    constructor(url: string) { streams.push(url); }
    addEventListener() {} removeEventListener() {} close() {}
  }
  vi.stubGlobal('fetch', fetcher); vi.stubGlobal('EventSource', Source);
  const stream = await import('@/api/ops-stream');
  function Crew() { stream.useCrewStream('datacenter'); return null; }
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(<QueryClientProvider client={qc}><Crew /></QueryClientProvider>);
  await waitFor(() => expect(fetcher).toHaveBeenCalledOnce());
  expect(fetcher.mock.calls[0]?.[0]).toBe('/api/v1/ops/technicians?site=datacenter');
  expect(fetcher.mock.calls[0]?.[1]?.method).toBeUndefined();
  expect(streams).toEqual(['/api/v1/ops/stream?site=datacenter']);
  view.unmount(); qc.clear();
});