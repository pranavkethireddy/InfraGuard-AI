import { useState, type ButtonHTMLAttributes } from 'react';
import type { FleetSummary, HealthStatus, MachineStatus, RackDetail, SiteMetric, HallMap, PowerState } from '@/api/fleet-types';
import { AppLink } from '@/lib/router-adapter';
import { serverPath, rackPath } from '@/api/parts-types';
import { ReadingsChart } from './ReadingsChart';
import { Badge, ConsoleButton, Empty, Mono, money } from './ui-kit';
import { facilityMetricUnit, facilityFaults, equipmentPath } from '@/api/facility-spec';
import { EquipmentDetails, EquipmentDirectory } from './FacilityEquipment';

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
export const powerClass = (power?: PowerState) => power === 'off' ? 'fill-background stroke-destructive' : power === 'at_risk' ? 'fill-attention-surface stroke-attention' : '';
export function PowerDetails({ item }: { item: { power_state?: PowerState; power_reason?: string | null; shutdown_eta_minutes?: number | null } }) {
  return <div className="mt-1 space-y-1 text-xs"><Badge tone={item.power_state === 'off' ? 'strong' : item.power_state === 'at_risk' ? 'attention' : 'neutral'}>Power: {item.power_state ?? 'Not reported'}</Badge>{item.power_reason && <p>{item.power_reason}</p>}{item.shutdown_eta_minutes != null && <p>Shutdown ETA: <Mono>{item.shutdown_eta_minutes}</Mono> DEMO minutes</p>}</div>;
}
export function FleetMetrics({ metrics, summary }: { metrics: SiteMetric[]; summary?: FleetSummary }) {
  return <div className="space-y-3">
    {summary && <>
      <dl className="flex flex-wrap gap-x-6 gap-y-2 border-b border-border pb-3">{(['healthy', 'warning', 'critical', 'no_data', 'open_incidents'] as const).map((key) => <div key={key}><dt className="eyebrow">{key.replaceAll('_', ' ')}</dt><dd className="font-mono text-lg">{summary[key]}</dd></div>)}</dl>
      <dl className="flex flex-wrap gap-6">{(['machines_powered_off', 'machines_at_risk_of_shutdown'] as const).map((key) => <div key={key}><dt className="eyebrow">{key.replaceAll('_', ' ')}</dt><dd className="font-mono text-lg">{summary[key] ?? 'Not reported'}</dd></div>)}</dl>
      <div className="overflow-x-auto"><table className="data-table"><caption className="sr-only">Fleet business case</caption><thead><tr><th>Cost if all fail</th><th>Cost to fix all now</th><th>Savings if fixed now</th></tr></thead><tbody><tr>{([summary.cost_if_all_fail, summary.cost_to_fix_all_now, summary.savings_if_fixed_now]).map((v, k) => <td key={k}><Mono>{v == null ? 'No data' : money(v, summary.currency)}</Mono></td>)}</tr></tbody></table></div>
      <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">Source details</summary><p className="mt-1 break-words">assumptions_source: {summary.assumptions_source ?? 'No data'}</p><p>Scenario repair/downtime estimates; not measured costs or actual billing.</p></details>
    </>}
    <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-3 lg:grid-cols-4">{metrics.map((m) => <div key={m.key} className="min-w-0 border-l border-border pl-3"><dt className="text-xs text-muted-foreground">{m.label}</dt><dd className="font-mono text-base">{m.value == null ? 'No data' : `${m.value} ${m.unit}`}</dd><dd className="mt-1 break-words text-[11px] text-muted-foreground"><details><summary className="cursor-pointer">Source details</summary><p className="mt-1">Source: {m.source}</p></details></dd></div>)}</dl>
  </div>;
}
export function FleetFloor({ halls, gridUnit, selected, onSelect, equipmentSelected = null, onEquipmentSelect, site = 'datacenter' }: { halls: HallMap[]; gridUnit: string; selected: string | null; onSelect: (id: string) => void; equipmentSelected?: string | null; onEquipmentSelect?: (id: string | null) => void; site?: string }) {
  return <div>
    <div className="mb-3 flex flex-wrap gap-3 text-xs" aria-label="Map status legend">{(['healthy', 'warning', 'critical', 'no_data'] as const).map((s) => <span key={s} className="flex items-center gap-1"><svg width="14" height="14" aria-hidden><rect width="12" height="12" x="1" y="1" className={healthClass[s]} /></svg>{s}</span>)}</div>
    <p className="mb-2 text-xs text-muted-foreground">Grid: {gridUnit}</p>
    <div aria-label="Map power legend" className="mb-4 flex flex-wrap gap-3 text-xs"><span>Power: on</span><span className="text-attention-foreground">at_risk · amber</span><span className="text-destructive">OFF · dark / red outline</span><span className="text-muted-foreground">? · Not reported</span><span>ETA: DEMO minutes</span></div>
    <div className="grid gap-4 md:grid-cols-2">{halls.map((hall) => <figure key={hall.hall_id} className="min-w-0">
      <figcaption className="mb-2 flex flex-wrap items-center gap-2 text-xs"><strong>{hall.name}</strong><Mono>{hall.width} × {hall.depth} cells</Mono><HealthBadge status={hall.status} /><span>{hall.kind}</span></figcaption>
      <svg viewBox={`0 0 ${hall.width} ${hall.depth}`} className="w-full border border-border bg-muted" role="group" aria-label={`${hall.name} floor map`}>
        <defs><pattern id={`grid-${hall.hall_id}`} width="1" height="1" patternUnits="userSpaceOnUse"><path d="M 1 0 L 0 0 0 1" fill="none" className="stroke-border" strokeWidth="0.03" /></pattern></defs>
        <rect width={hall.width} height={hall.depth} fill={`url(#grid-${hall.hall_id})`} />
        {hall.racks.map((r) => <g key={r.rack_id}>
          <rect role="button" tabIndex={0} aria-label={`${r.label}: ${r.status} · Power: ${r.power_state ?? 'Not reported'}${r.shutdown_eta_minutes != null ? ` · shutdown ETA ${r.shutdown_eta_minutes} DEMO minutes` : ''}`} aria-pressed={selected === r.rack_id} x={r.x} y={r.y} width={r.width} height={r.depth} className={`${healthClass[r.status]} ${powerClass(r.power_state)} cursor-pointer`} strokeWidth={selected === r.rack_id ? 0.16 : 0.07} onClick={() => onSelect(r.rack_id)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(r.rack_id); } }}><title>{r.label} · {r.status} · Power: {r.power_state ?? 'Not reported'} · {r.power_reason ?? r.reasons.join('; ')}</title></rect>
          <text x={r.x + r.width / 2} y={r.y + r.depth * 0.3} textAnchor="middle" dominantBaseline="middle" className="pointer-events-none fill-foreground font-mono" fontSize="0.25">{r.rack_id}</text>
          <text x={r.x + r.width / 2} y={r.y + r.depth * 0.55} textAnchor="middle" className="pointer-events-none fill-foreground font-mono" fontSize="0.19">{r.power_state === 'off' ? 'OFF' : r.power_state === 'at_risk' ? `AT RISK${r.shutdown_eta_minutes != null ? ` · ${r.shutdown_eta_minutes}m DEMO` : ''}` : r.power_state === 'on' ? 'ON' : 'Power ?'}</text>
          {hall.machines.filter((m) => m.placement.rack_id === r.rack_id).map((m, index, machines) => <g key={m.asset_id} role="img" aria-label={`${m.name}: ${m.status} · Power: ${m.power_state ?? 'Not reported'}${m.shutdown_eta_minutes != null ? ` · shutdown ETA ${m.shutdown_eta_minutes} DEMO minutes` : ''}`} className="pointer-events-none"><title>{m.asset_id} · {m.power_reason ?? 'Power reason not reported'}</title><circle cx={r.x + r.width * (index + 0.5) / machines.length} cy={r.y + r.depth * 0.8} r="0.09" className={`${healthClass[m.status]} ${powerClass(m.power_state)}`} strokeWidth="0.04" />{m.power_state === 'off' && <text x={r.x + r.width * (index + 0.5) / machines.length} y={r.y + r.depth * 0.98} textAnchor="middle" fontSize="0.11" className="fill-destructive">OFF</text>}</g>)}
        </g>)}
        {hall.machines.filter((m) => !m.placement.rack_id).map((m) => <g key={m.asset_id} role={onEquipmentSelect ? 'button' : 'img'} tabIndex={onEquipmentSelect ? 0 : undefined} aria-label={`${m.name}: ${m.status} · Power: ${m.power_state ?? 'Not reported'}`} aria-pressed={equipmentSelected === m.asset_id} className="cursor-pointer" onClick={() => onEquipmentSelect?.(m.asset_id)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onEquipmentSelect?.(m.asset_id); } }}><circle cx={m.placement.x} cy={m.placement.y} r="0.3" className={`${healthClass[m.status]} ${powerClass(m.power_state)}`} strokeWidth="0.06"><title>{m.name}: {m.status} · {m.power_reason ?? 'Power reason not reported'}</title></circle><text x={m.placement.x} y={m.placement.y + 0.55} textAnchor="middle" fontSize="0.2" className="pointer-events-none fill-foreground">{m.asset_id}</text></g>)}
      </svg>
    </figure>)}</div>
    {onEquipmentSelect && <EquipmentDirectory halls={halls} selected={equipmentSelected} onSelect={onEquipmentSelect} site={site} />}
  </div>;
}
// Explicit native units only; unknown readings do not become invented counts.
export function fieldUnit(field: string): string {
  const facility = facilityMetricUnit(field);
  if (facility) return facility;
  if (field.endsWith('_temp_c') || field === 'max_gpu_temp_c') return '°C';
  if (field.endsWith('_pct')) return '%';
  const suffix: Record<string, string> = { temperature_c: '°C', chip_temp_c: '°C', air_temperature_k: 'K', process_temperature_k: 'K', fan_speed_rpm: 'rpm', rotational_speed_rpm: 'rpm', hashrate_ths: 'TH/s', rated_hashrate_ths: 'TH/s', power_w: 'W', hw_error_pct: '%', power_on_hours: 'h', torque_nm: 'N·m', tool_wear_min: 'min' };
  const counts = ['ecc_errors', 'crc_errors', 'nic_crc_errors', 'gpus_online', 'gpus_throttled', 'psu_ok', 'nic_links_up', 'reallocated_sectors', 'pending_sectors', 'offline_uncorrectable', 'reported_uncorrectable', 'command_timeout', 'dimm_max_ecc'];
  if (counts.includes(field) || /^dimm\d+_ecc$/.test(field)) return 'count';
  if (['online', 'bmc_ok', 'nic1_link', 'nic2_link'].includes(field)) return 'binary 0/1';
  if (/^fan\d+_rpm$/.test(field) || field === 'min_fan_rpm') return 'rpm';
  if (/^psu\d+_w$/.test(field)) return 'W';
  return suffix[field] ?? 'Not provided';
}
export function FleetMachines({ machines, site = 'datacenter' }: { machines: MachineStatus[]; site?: string }) {
  const [page, setPage] = useState(0);
  const lastPage = Math.max(0, Math.ceil(machines.length / 25) - 1);
  const currentPage = Math.min(page, lastPage);
  const visible = machines.slice(currentPage * 25, (currentPage + 1) * 25);
  if (!machines.length) return <Empty>No machines returned.</Empty>;
  return <div>{machines.length > 25 && <div className="mb-3 flex flex-wrap items-center gap-3 text-xs"><span>{currentPage * 25 + 1}–{Math.min((currentPage + 1) * 25, machines.length)} of {machines.length} machines · backend order</span><ConsoleButton aria-label="Previous machines" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>←</ConsoleButton><ConsoleButton aria-label="Next machines" disabled={currentPage === lastPage} onClick={() => setPage(currentPage + 1)}>→</ConsoleButton></div>}<div className="overflow-x-auto"><table className="data-table"><caption className="sr-only">Machine status, backend ordering</caption><thead><tr><th>Machine</th><th>Status / fault</th><th>Latest readings</th><th>Incident / investigation</th></tr></thead><tbody>{visible.map((m) => <tr key={m.asset_id}>
    <td><AppLink to={m.asset_type === 'gpu_server' ? serverPath(m.asset_id) : facilityFaults[m.asset_type] ? equipmentPath(m.asset_id, site) : `/assets/${encodeURIComponent(m.asset_id)}`} className="font-mono text-primary underline">{m.asset_id}</AppLink><p>{m.name}</p><p className="text-xs text-muted-foreground">{m.asset_type} · {m.detector_id}</p></td>
    <td><HealthBadge status={m.status} /><PowerDetails item={m} />{m.simulated_fault && <p className="mt-1 text-xs text-attention-foreground">Simulated fault: {m.simulated_fault.kind} · {m.simulated_fault.phase}</p>}{m.work_order && <div className="mt-2 text-xs"><p>Work order: <Mono>{m.work_order.work_order_id}</Mono></p><p>{m.work_order.technician_name} · {m.work_order.technician_id}</p><p>{m.work_order.status} · {m.work_order.option ?? 'Option not reported'}</p><p>Progress: <Mono>{m.work_order.progress}</Mono></p><p>ETA: {m.work_order.eta_minutes == null ? 'Not reported' : `${m.work_order.eta_minutes} DEMO minutes`}</p></div>}</td>
    <td className="font-mono text-xs">{m.latest_values ? m.chart_fields.map((k) => <div key={k}>{k}: {m.latest_values?.[k] == null ? 'No data' : `${String(m.latest_values[k])} ${fieldUnit(k)}`}</div>) : 'No data'}<AppLink to={equipmentPath(m.asset_id, site)} className="mt-1 inline-block text-primary underline">All readings / history</AppLink></td>
    <td>{m.active_incident ? <><AppLink to={`/incidents/${m.active_incident.incident_id}`} className="font-mono text-primary underline">{m.active_incident.incident_id}</AppLink><p>{m.active_incident.title}</p><p className="text-xs">Investigation: {m.active_incident.investigation_status ?? 'Not queued'}</p></> : <span className="text-muted-foreground">None</span>}</td>
  </tr>)}</tbody></table></div></div>;
}
export function FleetRackPane({ rack, site = 'datacenter' }: { rack: RackDetail; site?: string }) {
  return <div className="space-y-3"><p><HealthBadge status={rack.status} /> <AppLink to={rackPath(rack.rack_id, site === 'mining' ? site : undefined)} className="text-primary underline">Open rack {rack.rack_id}</AppLink></p>
    <PowerDetails item={rack} />
    {(['pdu', 'tor'] as const).map((key) => <div key={key} className="border-t border-border pt-4"><h3 className="eyebrow mb-3">{key === 'pdu' ? 'Rack power · PDU' : 'Top-of-rack network · ToR'}</h3><p className="mb-3 text-xs">Returned ID: {rack[`${key}_id`] ? <AppLink to={equipmentPath(rack[`${key}_id`] ?? '', site)} className="font-mono text-primary underline">{rack[`${key}_id`]}</AppLink> : 'Not reported'}</p>{rack[key] ? <EquipmentDetails machine={rack[key]} site={site} /> : <Empty>Not reported</Empty>}</div>)}
    <ul className="list-disc pl-5 text-sm">{rack.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
    <p className="text-xs">Cooled by: {rack.cooled_by.map((id) => <AppLink key={id} to={`/assets/${id}`} className="mr-2 font-mono text-primary underline">{id}</AppLink>)}</p>
    <p className="text-xs">Incidents: {rack.open_incident_ids.length ? rack.open_incident_ids.map((id) => <AppLink key={id} to={`/incidents/${id}`} className="mr-2 font-mono text-primary underline">{id}</AppLink>) : 'None'}</p>
    <div className="text-sm"><h3 className="eyebrow">GPU servers</h3>{rack.server_ids?.length ? <ul className="mt-2 space-y-2">{rack.server_ids.map((id) => <li key={id}><AppLink to={serverPath(id)} className="font-mono text-primary underline">{id}</AppLink></li>)}</ul> : <p>{rack.server_ids ? 'No server IDs returned.' : 'Server IDs not reported.'}</p>}</div>
    <FleetMachines machines={rack.machines} site={site} />
    {rack.cooling_units.length > 0 && <><h3 className="eyebrow">Cooling units</h3><FleetMachines machines={rack.cooling_units} site={site} /></>}
    {[...rack.machines, ...rack.cooling_units].map((m) => <div key={m.asset_id}><h3 className="eyebrow mb-2">{m.asset_id} · returned history</h3><div className="grid gap-3 sm:grid-cols-2">{m.chart_fields.map((field) => <div key={field} className="min-w-0">{m.history.length ? <ReadingsChart readings={m.history.map((r) => ({ ...r, data_origin: 'simulated' }))} field={field} label={field.replaceAll('_', ' ')} unit={fieldUnit(field)} height={180} /> : <Empty>No history.</Empty>}</div>)}</div></div>)}
  </div>;
}