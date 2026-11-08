import type { GpuJob } from '@/api/fleet-types';
import { AppLink } from '@/lib/router-adapter';
import { Empty, Mono } from './ui-kit';
export function GpuJobs({ jobs }: { jobs: GpuJob[] | undefined }) {
  if (!jobs) return <Empty>GPU jobs not reported.</Empty>;
  if (!jobs.length) return <Empty>No GPU jobs returned.</Empty>;
  return <div className="max-w-full min-w-0 overflow-x-auto"><table className="data-table"><thead><tr><th>Job / row</th><th>Pace</th><th>GPUs / running / throttled</th><th>Servers down</th><th>Lost USD/hour</th><th>GPU-hour USD</th><th>Reasons / source</th></tr></thead><tbody>{jobs.map((j) => <tr key={j.job_id}>
    <td>{j.name}<p><Mono>{j.job_id} · {j.row}</Mono></p></td><td>{j.pace_pct == null ? 'Not reported' : `${j.pace_pct} %`}</td><td>{j.gpus} / {j.gpus_running} / {j.gpus_throttled}</td>
    <td>{j.servers_down.length ? j.servers_down.map((id) => <AppLink key={id} to={`/servers/${encodeURIComponent(id)}`} className="block font-mono text-primary underline">{id}</AppLink>) : 'None returned'}</td><td>{j.lost_usd_per_hour ?? 'Not reported'}</td><td>{j.gpu_hour_usd}</td>
    <td>{j.reasons.map((r) => <p key={r}>{r}</p>)}<p className="text-xs text-muted-foreground">Source: {j.assumptions_source} · demo price, not an actual bill.</p></td>
  </tr>)}</tbody></table></div>;
}