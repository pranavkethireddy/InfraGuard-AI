import type { ButtonHTMLAttributes } from 'react';
import type { FleetSummary, HealthStatus, MachineStatus, RackDetail, SiteMetric, HallMap } from '@/api/fleet-types';
import { AppLink } from '@/lib/router-adapter';
import { ReadingsChart } from './ReadingsChart';
import { Badge, ConsoleButton, Empty, Mono, money } from './ui-kit';

export function FleetButton({ primary, className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { primary?: boolean }) {
  return <ConsoleButton type="button" variant={primary ? 'primary' : 'outline'} className={className} {...props} />;
}
export const healthClass: Record<HealthStatus, string> = {
  healthy: 'fill-healthy-surface stroke-healthy', warning: 'fill-attention-surface stroke-attention',
  critical: 'fill-accent stroke-destructive', no_data: 'fill-muted stroke-rule-strong',
};
export function HealthBadge({ status }: { status: HealthStatus }) {
  return <Badge tone={status === 'critical' ? 'strong' : status === 'warning' ? 'attention' : status === 'healthy' ? 'healthy' : 'neutral'}>{status}</Badge>;
}
export function FleetMetrics({ metrics, summary }: { metrics: SiteMetric[]; summary?: FleetSummary }) {
  return <div className="space-y-3">
    {summary && <>
      <dl className="flex flex-wrap gap-x-6 gap-y-2 border-b border-border pb-3">{(['healthy', 'warning', 'critical', 'no_data', 'open_incidents'] as const).map((key) => <div key={key}><dt className="eyebrow">{key.replaceAll('_', ' ')}</dt><dd className="font-mono text-lg">{summary[key]}</dd></div>)}</dl>
      <div className="overflow-x-auto"><table className="data-table"><caption className="sr-only">Fleet business case</caption><thead><tr><th>Cost if all fail</th><th>Cost to fix all now</th><th>Savings if fixed now</th></tr></thead><tbody><tr>{([summary.cost_if_all_fail, summary.cost_to_fix_all_now, summary.savings_if_fixed_now]).map((v, k) => <td key={k}><Mono>{v == null ? 'No data' : money(v, summary.currency)}</Mono></td>)}</tr></tbody></table></div>
      <p className="text-xs text-muted-foreground">Demo repair/downtime assumptions · Source: {summary.assumptions_source ?? 'No data'}. Mining revenue provenance is reported separately below.</p>
    </>}
    <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-3 lg:grid-cols-4">{metrics.map((m) => <div key={m.key} className="min-w-0 border-l border-border pl-3"><dt className="text-xs text-muted-foreground">{m.label}</dt><dd className="font-mono text-base">{m.value == null ? 'No data' : `${m.value} ${m.unit}`}</dd><dd className="mt-1 break-words text-[11px] text-muted-foreground">Source: {m.source}</dd></div>)}</dl>
  </div>;
}
export function FleetFloor({ halls, gridUnit, selected, onSelect }: { halls: HallMap[]; gridUnit: string; selected: string | null; onSelect: (id: string) => void }) {
  return <div>
    <div className="mb-3 flex flex-wrap gap-3 text-xs" aria-label="Map status legend">{(['healthy', 'warning', 'critical', 'no_data'] as const).map((s) => <span key={s} className="flex items-center gap-1"><svg width="14" height="14" aria-hidden><rect width="12" height="12" x="1" y="1" className={healthClass[s]} /></svg>{s}</span>)}</div>
    <p className="mb-2 text-xs text-muted-foreground">Grid: {gridUnit}</p>
    <div className="grid gap-4 md:grid-cols-2">{halls.map((hall) => <figure key={hall.hall_id} className="min-w-0">
      <figcaption className="mb-2 flex flex-wrap items-center gap-2 text-xs"><strong>{hall.name}</strong><Mono>{hall.width} × {hall.depth} cells</Mono><HealthBadge status={hall.status} /><span>{hall.kind}</span></figcaption>
      <svg viewBox={`0 0 ${hall.width} ${hall.depth}`} className="w-full border border-border bg-muted" role="group" aria-label={`${hall.name} floor map`}>
        <defs><pattern id={`grid-${hall.hall_id}`} width="1" height="1" patternUnits="userSpaceOnUse"><path d="M 1 0 L 0 0 0 1" fill="none" className="stroke-border" strokeWidth="0.03" /></pattern></defs>
        <rect width={hall.width} height={hall.depth} fill={`url(#grid-${hall.hall_id})`} />
        {hall.racks.map((r) => <g key={r.rack_id}>
          <rect role="button" tabIndex={0} aria-label={`${r.label}: ${r.status}`} aria-pressed={selected === r.rack_id} x={r.x} y={r.y} width={r.width} height={r.depth} className={`${healthClass[r.status]} cursor-pointer`} strokeWidth={selected === r.rack_id ? 0.16 : 0.07} onClick={() => onSelect(r.rack_id)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(r.rack_id); } }}><title>{r.label} · {r.status} · {r.reasons.join('; ')}</title></rect>
          <text x={r.x + r.width / 2} y={r.y + r.depth / 2} textAnchor="middle" dominantBaseline="middle" className="pointer-events-none fill-foreground font-mono" fontSize="0.3">{r.rack_id}</text>
        </g>)}
        {hall.machines.filter((m) => !m.placement.rack_id).map((m) => <g key={m.asset_id}><circle cx={m.placement.x} cy={m.placement.y} r="0.35" className={healthClass[m.status]} strokeWidth="0.06"><title>{m.name}: {m.status}</title></circle><text x={m.placement.x + 0.5} y={m.placement.y} fontSize="0.35" className="fill-foreground font-mono">{m.asset_id}</text></g>)}
      </svg>
    </figure>)}</div>
  </div>;
}
// Units are encoded in contract field names; no reading, score or financial value is calculated.
export function fieldUnit(field: string): string {
  const suffix: Record<string, string> = { temperature_c: '°C', chip_temp_c: '°C', air_temperature_k: 'K', process_temperature_k: 'K', fan_speed_rpm: 'rpm', rotational_speed_rpm: 'rpm', hashrate_ths: 'TH/s', rated_hashrate_ths: 'TH/s', power_w: 'W', hw_error_pct: '%', power_on_hours: 'h', torque_nm: 'N·m', tool_wear_min: 'min' };
  return suffix[field] ?? 'count';
}
export function FleetMachines({ machines }: { machines: MachineStatus[] }) {
  if (!machines.length) return <Empty>No machines returned.</Empty>;
  return <div className="overflow-x-auto"><table className="data-table"><caption className="sr-only">Machine status, backend ordering</caption><thead><tr><th>Machine</th><th>Status / simulated fault</th><th>Latest readings</th><th>Incident / investigation</th></tr></thead><tbody>{machines.map((m) => <tr key={m.asset_id}>
    <td><AppLink to={`/assets/${m.asset_id}`} className="font-mono text-primary underline">{m.asset_id}</AppLink><p>{m.name}</p><p className="text-xs text-muted-foreground">{m.asset_type} · {m.detector_id}</p></td>
    <td><HealthBadge status={m.status} />{m.simulated_fault && <p className="mt-1 text-xs text-attention-foreground">Simulated fault: {m.simulated_fault.kind} · {m.simulated_fault.phase}</p>}</td>
    <td className="font-mono text-xs">{m.latest_values ? Object.entries(m.latest_values).map(([k, v]) => <div key={k}>{k}: {v == null ? 'No data' : `${String(v)} ${fieldUnit(k)}`}</div>) : 'No data'}</td>
    <td>{m.active_incident ? <><AppLink to={`/incidents/${m.active_incident.incident_id}`} className="font-mono text-primary underline">{m.active_incident.incident_id}</AppLink><p>{m.active_incident.title}</p><p className="text-xs">Investigation: {m.active_incident.investigation_status ?? 'Not queued'}</p></> : <span className="text-muted-foreground">None</span>}</td>
  </tr>)}</tbody></table></div>;
}
export function FleetRackPane({ rack }: { rack: RackDetail }) {
  return <div className="space-y-3"><p><HealthBadge status={rack.status} /> <Mono>{rack.rack_id}</Mono></p>
    <ul className="list-disc pl-5 text-sm">{rack.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
    <p className="text-xs">Cooled by: {rack.cooled_by.map((id) => <AppLink key={id} to={`/assets/${id}`} className="mr-2 font-mono text-primary underline">{id}</AppLink>)}</p>
    <p className="text-xs">Incidents: {rack.open_incident_ids.length ? rack.open_incident_ids.map((id) => <AppLink key={id} to={`/incidents/${id}`} className="mr-2 font-mono text-primary underline">{id}</AppLink>) : 'None'}</p>
    <FleetMachines machines={rack.machines} />
    {rack.cooling_units.length > 0 && <><h3 className="eyebrow">Cooling units</h3><FleetMachines machines={rack.cooling_units} /></>}
    {[...rack.machines, ...rack.cooling_units].map((m) => <div key={m.asset_id}><h3 className="eyebrow mb-2">{m.asset_id} · returned history</h3><div className="grid gap-3 sm:grid-cols-2">{m.chart_fields.map((field) => <div key={field} className="min-w-0">{m.history.length ? <ReadingsChart readings={m.history.map((r) => ({ ...r, data_origin: 'simulated' }))} field={field} label={field.replaceAll('_', ' ')} unit={fieldUnit(field)} height={180} /> : <Empty>No history.</Empty>}</div>)}</div></div>)}
  </div>;
}