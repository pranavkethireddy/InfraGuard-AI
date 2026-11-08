import { useState } from 'react';
import type { HallMap, MachineStatus } from '@/api/fleet-types';
import { equipmentPath, facilityMetricUnit } from '@/api/facility-spec';
import { serverPath, rackPath } from '@/api/parts-types';
import { AppLink } from '@/lib/router-adapter';
import { ReadingsChart } from './ReadingsChart';
import { ConsoleButton, Empty, Mono, SourceDetails, dt, inputCls } from './ui-kit';
import { HealthBadge, PowerDetails, fieldUnit } from './FleetWorkspace';

export function EquipmentDetails({ machine, site = 'datacenter' }: { machine: MachineStatus; site?: string }) {
  const fields = Array.from(new Set([...machine.chart_fields, ...Object.keys(machine.latest_values ?? {}), ...machine.history.flatMap((p) => Object.keys(p.values))]));
  return <div className="space-y-4" role="region" aria-label={`Equipment details · ${machine.asset_id}`}>
    <div className="flex flex-wrap items-center gap-3"><strong>{machine.name}</strong><Mono>{machine.asset_id}</Mono><HealthBadge status={machine.status} /><span className="text-xs">{machine.asset_type}</span></div>
    <p className="text-xs text-muted-foreground">{machine.location} · Observed: {machine.last_reading_at ?? 'Not reported'}</p>
    <PowerDetails item={machine} />
    <nav className="flex flex-wrap gap-4 text-sm" aria-label="Equipment links"><AppLink to={equipmentPath(machine.asset_id, site)} className="text-primary underline">Open equipment</AppLink><AppLink to={`/assets/${encodeURIComponent(machine.asset_id)}`} className="text-primary underline">Asset record</AppLink>{machine.asset_type === 'gpu_server' && <AppLink to={serverPath(machine.asset_id)} className="text-primary underline">Server / GPUs</AppLink>}{machine.placement.rack_id && <AppLink to={rackPath(machine.placement.rack_id, site)} className="text-primary underline">Parent rack</AppLink>}{machine.active_incident && <AppLink to={`/incidents/${encodeURIComponent(machine.active_incident.incident_id)}`} className="text-primary underline">Incident · {machine.active_incident.title}</AppLink>}</nav>
    <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{fields.map((field) => <div key={field} className="min-w-0 border-l border-border pl-3"><dt className="break-words text-xs text-muted-foreground">{field}</dt><dd className="font-mono text-sm">{machine.latest_values?.[field] == null ? 'Not reported' : String(machine.latest_values[field])} <span className="text-xs text-muted-foreground">{facilityMetricUnit(field) ?? fieldUnit(field)}</span></dd></div>)}</dl>
    {!machine.latest_values && <Empty>Latest metrics not reported.</Empty>}
    <details><summary className="cursor-pointer text-sm">Reading history</summary><div className="mt-4 grid gap-4 sm:grid-cols-2">{machine.chart_fields.map((field) => <div key={field} className="min-w-0"><h4 className="break-words text-xs">{field} · {fieldUnit(field)}</h4>{machine.history.length ? <ReadingsChart readings={machine.history.map((p) => ({ ...p, data_origin: 'simulated' }))} field={field} label={field} unit={fieldUnit(field)} height={180} /> : <Empty>No history returned.</Empty>}</div>)}</div>{machine.history.length > 0 && <div className="mt-4 overflow-x-auto"><table className="data-table"><caption className="sr-only">Equipment reading history</caption><thead><tr><th>Observed (UTC)</th>{fields.map((f) => <th key={f}>{f} · {fieldUnit(f)}</th>)}</tr></thead><tbody>{machine.history.map((p, i) => <tr key={`${p.observed_at}-${i}`}><td>{dt(p.observed_at)}</td>{fields.map((f) => <td key={f}>{p.values[f] == null ? 'Not reported' : String(p.values[f])}</td>)}</tr>)}</tbody></table></div>}</details>
    <SourceDetails><p>data_origin: simulated · synthetic facility scenario; not production observations.</p><p>Native metric units follow the approved reading specification; unknown units are Not provided. No conversions applied.</p>{machine.simulated_fault && <p>Fault: {machine.simulated_fault.kind} · {machine.simulated_fault.phase}</p>}</SourceDetails>
  </div>;
}

export function EquipmentDirectory({ halls, selected, onSelect, site = 'datacenter' }: { halls: HallMap[]; selected: string | null; onSelect: (id: string | null) => void; site?: string }) {
  const [category, setCategory] = useState('all');
  const [room, setRoom] = useState('all');
  const [search, setSearch] = useState('');
  // IDs are authoritative; PDU/ToR also occur outside rack.machine_ids.
  const machines = Array.from(new Map(halls.flatMap((h) => h.machines).map((m) => [m.asset_id, m])).values());
  const categories = Array.from(new Set(machines.map((m) => m.asset_type)));
  const visible = machines.filter((m) => (category === 'all' || m.asset_type === category) && (room === 'all' || m.placement.hall_id === room) && `${m.name} ${m.asset_id}`.toLowerCase().includes(search.toLowerCase()));
  const picked = machines.find((m) => m.asset_id === selected);
  return <div className="mt-4 space-y-4 border-t border-border pt-4">
    <div className="flex flex-wrap items-end gap-3"><label className="text-xs">Equipment category<select aria-label="Equipment category" className={`${inputCls} mt-1`} value={category} onChange={(e) => setCategory(e.target.value)}><option value="all">All equipment</option>{categories.map((c) => <option key={c} value={c}>{c.replaceAll('_', ' ')}</option>)}</select></label><label className="text-xs">Room<select aria-label="Equipment room" className={`${inputCls} mt-1`} value={room} onChange={(e) => setRoom(e.target.value)}><option value="all">All rooms</option>{halls.map((h) => <option key={h.hall_id} value={h.hall_id}>{h.name}</option>)}</select></label><label className="min-w-0 text-xs">Equipment ID / name<input aria-label="Find equipment" className={`${inputCls} mt-1`} value={search} onChange={(e) => setSearch(e.target.value)} /></label></div>
    <p className="text-xs text-muted-foreground" role="status">{visible.length} of {machines.length} returned equipment</p>
    <ul aria-label="Facility equipment inventory" className="grid max-h-80 gap-2 overflow-y-auto sm:grid-cols-2 lg:grid-cols-3">{visible.map((m) => <li key={m.asset_id} className="min-w-0"><ConsoleButton aria-pressed={selected === m.asset_id} className="h-full min-h-11 w-full justify-start whitespace-normal text-left" onClick={() => onSelect(m.asset_id)}><span className="min-w-0"><span className="block break-words font-mono text-xs">{m.asset_id} · {m.status}</span><span className="block text-xs text-muted-foreground">{m.name} · {m.asset_type.replaceAll('_', ' ')}</span></span></ConsoleButton></li>)}</ul>
    {!visible.length && <Empty>No equipment matches the selected filters.</Empty>}
    {picked && <div className="border-t border-border pt-4"><ConsoleButton className="mb-3" aria-label="Close equipment details" onClick={() => onSelect(null)}>×</ConsoleButton><EquipmentDetails machine={picked} site={site} /></div>}
  </div>;
}