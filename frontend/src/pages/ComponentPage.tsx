import { useQuery } from '@tanstack/react-query';
import { serverComponentQuery } from '@/api/parts-queries';
import { serverQuery } from '@/api/gpu-queries';
import { metricUnit, rackPath, serverPath } from '@/api/parts-types';
import { ComponentMetrics } from '@/components/ServerParts';
import { FailureModePanel } from '@/components/FailureModePanel';
import { ReadingsChart } from '@/components/ReadingsChart';
import { Empty, ErrorState, Loading, PageHeader, SourceDetails } from '@/components/ui-kit';
import { AppLink } from '@/lib/router-adapter';
export function ComponentPage({ id, cid }: { id: string; cid: string }) {
  const q = useQuery(serverComponentQuery(id, cid));
  const server = useQuery(serverQuery(id));
  const navigation = <nav aria-label="Part navigation" className="mb-5 flex flex-wrap gap-4 text-sm"><AppLink to={serverPath(id)} className="text-primary underline">Parent server · {id}</AppLink>{server.data && <AppLink to={rackPath(server.data.rack_id)} className="text-primary underline">Rack {server.data.rack_id}</AppLink>}</nav>;
  if (q.isLoading) return <>{navigation}<Loading label="Loading part…" /></>;
  if (!q.data) return <>{navigation}<ErrorState error={q.error} title="Could not load server part" /></>;
  const d = q.data;
  const metrics = Array.from(new Set([...Object.keys(d.component.metrics), ...d.history.flatMap((h) => Object.keys(h.metrics))]));
  const observed = d.history.at(-1)?.observed_at;
  return <>{navigation}<PageHeader title={d.component.name} meta={<span className="break-all">{d.server_id} · {d.component.component_id} · {d.component.kind} · Observed: <time>{observed ?? 'Not reported'}</time></span>} actions={<span className="text-sm">Status: {d.component.status}</span>} />
    {q.error && <ErrorState error={q.error} />}
    <div className="space-y-6">
      <div className="max-w-xl"><ComponentMetrics component={d.component} />{d.component.note && <p className="mt-3 text-sm">{d.component.note}</p>}</div>
      <div><h2 className="mb-3 text-sm font-semibold">Metric history</h2><div className="grid gap-6 lg:grid-cols-2">{metrics.map((metric) => <div key={metric} className="min-w-0"><h3 className="text-sm">{metric} · {metricUnit(metric) ?? 'unit not provided'}</h3>{d.history.some((h) => typeof h.metrics[metric] === 'number') ? <ReadingsChart readings={d.history.map((h) => ({ observed_at: h.observed_at, values: h.metrics, data_origin: 'simulated' }))} field={metric} unit={metricUnit(metric) ?? 'unit not provided'} label={metric} /> : <Empty>No history returned for this metric.</Empty>}</div>)}</div>
        {!metrics.length && <Empty>No metrics returned.</Empty>}
        <div className="mt-4 overflow-x-auto"><table className="data-table"><caption className="sr-only">Part history</caption><thead><tr><th>Observed (UTC)</th><th>Status</th>{metrics.map((m) => <th key={m}>{m} · {metricUnit(m) ?? 'unit not provided'}</th>)}</tr></thead><tbody>{d.history.map((h, i) => <tr key={i}><td>{h.observed_at}</td><td>{h.status}</td>{metrics.map((m) => <td key={m}>{h.metrics[m] == null ? 'Not reported' : String(h.metrics[m])}</td>)}</tr>)}</tbody></table></div>
        {!d.history.length && <Empty>No history returned.</Empty>}
      </div>
      <div><h2 className="mb-4 text-sm font-semibold">Repair playbook</h2><FailureModePanel mode={d.failure_mode} /></div>
      <SourceDetails><p>Returned component telemetry and playbook; fixture preview is illustrative, not live. Missing samples are not interpolated.</p></SourceDetails>
    </div>
  </>;
}