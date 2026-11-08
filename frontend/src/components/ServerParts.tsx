import { useQuery } from '@tanstack/react-query';
import { serverComponentsQuery } from '@/api/parts-queries';
import { componentPath, metricUnit } from '@/api/parts-types';
import type { ComponentKind, ComponentStatus, ServerComponent } from '@/api/parts-types';
import { AppLink } from '@/lib/router-adapter';
import { Empty, ErrorState, Loading } from './ui-kit';
export const componentStatusClass: Record<ComponentStatus, string> = { ok: 'border-healthy text-healthy-foreground', warning: 'border-attention text-attention-foreground', failed: 'border-destructive text-destructive', offline: 'border-rule-strong text-muted-foreground' };
export function ComponentMetrics({ component }: { component: ServerComponent }) {
  const entries = Object.entries(component.metrics);
  return entries.length ? <dl className="space-y-1 text-xs">{entries.map(([key, value]) => <div key={key} className="flex flex-wrap justify-between gap-2"><dt className="break-all text-muted-foreground">{key}</dt><dd className="font-mono">{value == null ? 'Not reported' : String(value)} {metricUnit(key) ?? 'unit not provided'}</dd></div>)}</dl> : <p className="text-xs">Metrics: Not reported</p>;
}
export function ServerParts({ id }: { id: string }) {
  const q = useQuery(serverComponentsQuery(id));
  if (q.isLoading) return <Loading label="Loading server parts…" />;
  if (!q.data) return <ErrorState error={q.error} title="Could not load server parts" />;
  const data = q.data;
  // Group only kinds actually returned, preserving the returned order within each group.
  const kinds = Array.from(new Set(data.components.map((c) => c.kind)));
  const names: Record<ComponentKind, string> = { gpu: 'GPUs', cpu: 'CPUs', dimm: 'Memory', fan: 'Fans', psu: 'Power supplies', nic: 'Network', nvme: 'Storage', bmc: 'Management' };
  return <div className="space-y-5" role="region" aria-label="Server parts">
    <p className="break-words text-xs text-muted-foreground">{data.components.length} returned parts · Observed: <time>{data.observed_at ?? 'Not reported'}</time></p>
    {q.error && <ErrorState error={q.error} />}
    {!data.components.length && <Empty>No components returned.</Empty>}
    {kinds.map((kind) => <div key={kind} role="group" aria-label={names[kind]}><h3 className="eyebrow mb-3">{names[kind]}</h3><div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{data.components.filter((c) => c.kind === kind).map((c) => <AppLink key={c.component_id} to={componentPath(data.server_id, c.component_id)} className={`min-w-0 rounded-lg border bg-muted p-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary ${componentStatusClass[c.status]}`}><div className="mb-2 flex flex-wrap justify-between gap-2"><strong className="text-sm">{c.name}</strong><span className="text-xs">{c.status}</span></div><p className="mb-2 break-all font-mono text-xs text-muted-foreground">{c.component_id}</p><ComponentMetrics component={c} />{c.note && <p className="mt-2 break-words text-xs">{c.note}</p>}</AppLink>)}</div></div>)}
  </div>;
}