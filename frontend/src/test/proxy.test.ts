// @vitest-environment node
import { afterEach, expect, it } from 'vitest';
import { createServer as createHttpServer, type Server } from 'node:http';
import { createServer, type ViteDevServer } from 'vite';
import config from '../../vite.config';

let upstream: Server | undefined;
let vite: ViteDevServer | undefined;
afterEach(async () => {
  await vite?.close(); vite = undefined;
  await new Promise<void>((resolve, reject) => { if (!upstream) return resolve(); upstream.close((error) => error ? reject(error) : resolve()); });
  upstream = undefined;
});

it('preserves /api/v1 and stream queries through the same-origin Vite proxy', async () => {
  const requests: string[] = [];
  upstream = createHttpServer((req, res) => {
    requests.push(req.url ?? '');
    if (req.url?.includes('/ops/stream')) { res.writeHead(200, { 'Content-Type': 'text/event-stream' }); res.end('event: crew\ndata: {"demo_time":"returned"}\n\n'); }
    else { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end('{"sites":[]}'); }
  });
  await new Promise<void>((resolve) => upstream?.listen(0, '127.0.0.1', resolve));
  const address = upstream.address();
  if (!address || typeof address === 'string') throw new Error('No upstream port');
  expect(config.server?.host).toBe('0.0.0.0');
  const proxy = config.server?.proxy?.['/api'];
  if (!proxy || typeof proxy === 'string') throw new Error('Missing API proxy');
  expect(proxy.target).toBe('http://127.0.0.1:8000');
  vite = await createServer({ ...config, configFile: false, plugins: [], server: { ...config.server, host: '127.0.0.1', port: 0, proxy: { '/api': { ...proxy, target: `http://127.0.0.1:${address.port}` } } } });
  await vite.listen();
  const local = vite.httpServer?.address();
  if (!local || typeof local === 'string') throw new Error('No proxy port');
  const origin = `http://127.0.0.1:${local.port}`;
  const sites = await fetch(`${origin}/api/v1/fleet/sites`);
  expect(await sites.json()).toEqual({ sites: [] });
  const stream = await fetch(`${origin}/api/v1/ops/stream?site=mining`);
  expect(stream.headers.get('content-type')).toBe('text/event-stream');
  expect(await stream.text()).toContain('event: crew\ndata: {"demo_time":"returned"}');
  expect(requests).toEqual(['/api/v1/fleet/sites', '/api/v1/ops/stream?site=mining']);
}, 15000);