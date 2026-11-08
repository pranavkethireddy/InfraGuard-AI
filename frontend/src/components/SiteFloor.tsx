import { useState } from 'react';
import type { HallMap } from '@/api/fleet-types';
import type { FloorPlan, Technician } from '@/api/ops-types';
import { AppLink } from '@/lib/router-adapter';
import { Badge, ConsoleButton, Fields } from './ui-kit';
import { FleetFloor, healthClass, powerClass } from './FleetWorkspace';
import { EquipmentDirectory } from './FacilityEquipment';

export function TechnicianDetails({ technician }: { technician: Technician }) {
  const task = technician.current_work_order;
  return <div className="space-y-3">
    <h3 className="font-semibold">{technician.name}</h3><Badge>{technician.status}</Badge><Badge>Device-controlled: {technician.device_controlled == null ? 'Not reported' : technician.device_controlled ? 'Yes' : 'No'}</Badge>
    <Fields rows={[["Task", task?.title ?? 'None returned'], ["Work status", task?.status ?? 'No current work'], ["Position", technician.position ? `${technician.position.x}, ${technician.position.y} · ${technician.position.hall_id ?? 'corridor'}` : 'Coordinates unavailable'], ["Work spot", task?.spot ? `${task.spot.x}, ${task.spot.y}` : 'Not reported'], ["Asset", task?.asset_name ?? task?.asset_id ?? 'Not reported'], ["Walking", `${technician.walking_minutes_left ?? 'Not reported'} DEMO minutes`]]} />
    {task?.asset_id && <AppLink to={`/assets/${encodeURIComponent(task.asset_id)}`} className="mr-4 text-primary underline">Asset</AppLink>}
    {task?.incident_id && <AppLink to={`/incidents/${encodeURIComponent(task.incident_id)}`} className="mr-4 text-primary underline">Incident / why</AppLink>}
    <AppLink to={`/pager?technician=${encodeURIComponent(technician.technician_id)}`} className="inline-flex min-h-11 items-center text-primary underline">Open pager · task and assignment reason</AppLink>
  </div>;
}
export function SiteFloor({ floor, halls, technicians, selected, onSelect, equipmentSelected = null, onEquipmentSelect, site = 'datacenter' }: { floor: FloorPlan; halls: HallMap[]; technicians: Technician[]; selected: string | null; onSelect: (id: string) => void; equipmentSelected?: string | null; onEquipmentSelect?: (id: string | null) => void; site?: string }) {
  const [techId, setTechId] = useState<string | null>(null);
  const [roomId, setRoomId] = useState('');
  const room = halls.find((h) => h.hall_id === roomId);
  const picked = technicians.find((t) => t.technician_id === techId);
  return <div className="space-y-4">
    <div className="flex flex-wrap gap-3 text-xs"><span>Grid: {floor.grid_unit}</span>{(['healthy', 'warning', 'critical', 'no_data'] as const).map((s) => <Badge key={s} tone={s === 'healthy' ? 'healthy' : s === 'warning' ? 'attention' : s === 'critical' ? 'strong' : 'neutral'}>{s}</Badge>)}<span>Power: on / at_risk / OFF / not reported</span></div>
    <div className="max-w-full overflow-x-auto">
      <svg viewBox={`0 0 ${floor.width} ${floor.depth}`} className="min-w-[640px] w-full border border-border bg-background" role="group" aria-label={`${floor.site_id} site floor plan`}>
        <defs><pattern id={`site-grid-${floor.site_id}`} width="1" height="1" patternUnits="userSpaceOnUse"><path d="M 1 0 L 0 0 0 1" fill="none" className="stroke-border" strokeWidth="0.025" /></pattern></defs>
        <rect width={floor.width} height={floor.depth} fill={`url(#site-grid-${floor.site_id})`} />
        <path d={`M 0 ${floor.corridor_y} H ${floor.width}`} className="stroke-rule-strong" strokeWidth="0.12"><title>Service corridor</title></path>
        {floor.halls.map((f) => {
          const hall = halls.find((h) => h.hall_id === f.hall_id);
          return <g key={f.hall_id}>
            <g transform={`translate(${f.x} ${f.y})`} data-hall={f.hall_id}>
              <rect width={f.width} height={f.depth} className="fill-muted stroke-border" strokeWidth="0.06" />
              <text x="0.6" y="0.7" fontSize="0.42" className="fill-foreground">{f.name}</text>
              <path d={`M ${floor.lane_offset} 1 V ${f.depth}`} className="stroke-rule-strong" strokeWidth="0.05" strokeDasharray="0.2 0.2" />
              {hall?.racks.map((r) => <g key={r.rack_id}>
                <rect x={r.x} y={r.y} width={r.width} height={r.depth} role="button" tabIndex={0} aria-label={`${r.label}: ${r.status} · Power: ${r.power_state ?? 'Not reported'}`} aria-pressed={selected === r.rack_id} className={`${healthClass[r.status]} ${powerClass(r.power_state)} cursor-pointer focus:stroke-primary`} strokeWidth={selected === r.rack_id ? 0.18 : 0.07} onClick={() => onSelect(r.rack_id)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(r.rack_id); } }}><title>{r.rack_id} · {r.status} · {r.power_reason ?? r.reasons.join('; ')}</title></rect>
                <text x={r.x + r.width / 2} y={r.y + r.depth / 2} textAnchor="middle" fontSize="0.24" className="pointer-events-none fill-foreground font-mono">{r.rack_id}</text>
                <text x={r.x + r.width / 2} y={r.y + r.depth * .8} textAnchor="middle" fontSize="0.18" className="pointer-events-none fill-foreground">{r.status} · {r.power_state ?? '?'}</text>
              </g>)}
              {hall?.machines.filter((m) => !m.placement.rack_id).map((m) => <circle key={m.asset_id} data-equipment={m.asset_id} role={onEquipmentSelect ? 'button' : 'img'} tabIndex={onEquipmentSelect ? 0 : undefined} aria-label={`${m.name}: ${m.status} · ${m.asset_type}`} aria-pressed={equipmentSelected === m.asset_id} cx={m.placement.x} cy={m.placement.y} r="0.22" className={`${healthClass[m.status]} ${powerClass(m.power_state)} cursor-pointer`} strokeWidth="0.06" onClick={() => onEquipmentSelect?.(m.asset_id)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onEquipmentSelect?.(m.asset_id); } }}><title>{m.asset_id} · {m.status} · {m.asset_type} · {m.power_reason ?? 'Power not reported'}</title></circle>)}
              {!hall && <text x="0.6" y="1.5" fontSize="0.32" className="fill-muted-foreground">Equipment not reported</text>}
            </g>
            <path d={`M ${f.door.x} ${f.door.y} V ${floor.corridor_y}`} className="stroke-rule-strong" strokeWidth="0.08" />
            <circle cx={f.door.x} cy={f.door.y} r="0.22" className="fill-chart-line"><title>{f.name} door</title></circle>
          </g>;
        })}
        {technicians.map((t) => <g key={t.technician_id}>
          {!!t.path?.length && <polyline data-technician-path={t.technician_id} points={t.path.map((p) => `${p.x},${p.y}`).join(' ')} fill="none" className="stroke-primary" strokeWidth="0.09" strokeDasharray="0.25 0.12"><title>{t.name} returned walking waypoints</title></polyline>}
          {t.position && <g role="button" tabIndex={0} aria-label={`${t.name}: ${t.status} · ${t.current_work_order?.title ?? 'No current task'}`} aria-pressed={techId === t.technician_id} className="cursor-pointer focus:outline-none" onClick={() => setTechId(t.technician_id)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setTechId(t.technician_id); } }}>
            <circle data-technician={t.technician_id} cx={t.position.x} cy={t.position.y} r="0.38" className="fill-primary stroke-foreground" strokeWidth={techId === t.technician_id ? '.16' : '.07'} />
            <text x={t.position.x + .5} y={t.position.y} fontSize="0.4" className="fill-foreground">{t.name}</text>
          </g>}
        </g>)}
      </svg>
    </div>
    <div className="flex flex-wrap items-center gap-3"><label className="text-xs">Room map<select aria-label="Focused room map" className="ml-2 rounded-sm border border-input bg-background p-2 text-foreground" value={roomId} onChange={(e) => setRoomId(e.target.value)}><option value="">Site overview</option>{halls.map((h) => <option key={h.hall_id} value={h.hall_id}>{h.name} · {h.status}</option>)}</select></label></div>
    {room && <FleetFloor halls={[room]} gridUnit={floor.grid_unit} selected={selected} onSelect={onSelect} />}
    {onEquipmentSelect && <EquipmentDirectory halls={halls} selected={equipmentSelected} onSelect={onEquipmentSelect} site={site} />}
    <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3" aria-label="Technician text list">{technicians.map((t) => <li key={t.technician_id}><ConsoleButton className="min-h-11 w-full justify-start whitespace-normal text-left" onClick={() => setTechId(t.technician_id)}>{t.name} · {t.status}</ConsoleButton><p className="mt-1 text-xs text-muted-foreground">{t.position ? `${t.position.x}, ${t.position.y}` : 'Coordinates unavailable'} · {t.walking_minutes_left ?? 'Not reported'} DEMO walking minutes · device-controlled: {t.device_controlled == null ? 'Not reported' : t.device_controlled ? 'Yes' : 'No'}</p></li>)}</ul>
    {picked && <div role="region" aria-label="Selected technician" className="border-t border-border pt-4"><ConsoleButton aria-label="Close technician details" className="mb-3 min-h-11" onClick={() => setTechId(null)}>×</ConsoleButton><TechnicianDetails technician={picked} /></div>}
  </div>;
}