import type { Asset, IncidentSummary } from "@/api/types";
import { AppLink } from "@/lib/router-adapter";
import { Badge, Mono, OriginBadge, RiskBadge, SCORE_KIND_LABEL, StatusBadge, dt, val } from "./ui-kit";
import { RankValue } from './PriorityRank';

export function EquipmentTable({ assets }: { assets: Asset[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="data-table">
        <caption className="sr-only">Equipment</caption>
        <thead>
          <tr><th>Asset</th><th>Type</th><th>Location</th><th>Criticality</th><th>Risk</th><th>Active incident</th><th>Detector</th><th>Data</th><th>Last reading</th></tr>
        </thead>
        <tbody>
          {assets.map((a) => (
            <tr key={a.asset_id}>
              <td>
                <AppLink to={`/assets/${a.asset_id}`} className="whitespace-nowrap font-medium text-foreground underline-offset-2 hover:text-primary hover:underline">{a.name}</AppLink>
                <div className="whitespace-nowrap font-mono text-[11.5px] text-muted-foreground">{a.asset_id}</div>
                {a.asset_type === 'gpu_server' && <AppLink to={`/servers/${encodeURIComponent(a.asset_id)}`} className="block text-xs text-primary underline">Server / GPUs</AppLink>}
              </td>
              <td><Mono>{a.asset_type}</Mono></td>
              <td>{a.location}</td>
              <td className="capitalize">{a.criticality}</td>
              <td><RiskBadge level={a.current_risk_level} /></td>
              <td>{a.active_incident_id ? <AppLink to={`/incidents/${a.active_incident_id}`} className="font-mono text-[12.5px] text-primary underline underline-offset-2">{a.active_incident_id}</AppLink> : <span className="text-muted-foreground">—</span>}</td>
              <td className="whitespace-nowrap"><Mono>{a.compatible_detector ?? "—"}</Mono></td>
              <td><OriginBadge origin={a.data_origin} /></td>
              <td className="whitespace-nowrap"><Mono>{dt(a.last_reading_at)}</Mono></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Incidents in the order the API returned them; priority_index is server-calculated. */
export function IncidentQueue({ incidents, compact = false }: { incidents: IncidentSummary[]; compact?: boolean }) {
  if (compact) return (
    <ul className="divide-y divide-border">
      {incidents.map((i) => <li key={i.incident_id} className="space-y-3 p-5">
        <div className="flex flex-wrap items-center gap-2"><RiskBadge level={i.risk_level} /><StatusBadge status={i.status} /></div>
        <AppLink to={`/incidents/${i.incident_id}`} className="block text-sm font-semibold leading-relaxed hover:text-primary">{i.title}</AppLink>
        <p className="break-all font-mono text-[11px] text-muted-foreground">{i.incident_id} · {i.asset_id}</p>
        <div className="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground"><span>Priority rank <RankValue rank={i.priority_rank} /></span><span>{dt(i.opened_at)}</span></div>
      </li>)}
    </ul>
  );
  return (
    <div className="overflow-x-auto">
      <table className="data-table">
        <caption className="sr-only">Incident queue</caption>
        <thead>
          <tr>
            <th>Priority rank</th><th className="text-right">Priority idx</th><th>Incident</th><th>Status</th><th>Risk</th>
            {!compact && <><th>Score type</th><th>Detector</th><th>Data</th><th className="text-right">Predictions</th></>}
            <th>Opened</th>
          </tr>
        </thead>
        <tbody>
          {incidents.map((i) => (
            <tr key={i.incident_id}>
              <td><RankValue rank={i.priority_rank} /></td>
              <td className="text-right"><Mono>{val(i.priority_index)}</Mono></td>
              <td className="min-w-[14rem]">
                <AppLink to={`/incidents/${i.incident_id}`} className="font-medium text-foreground underline-offset-2 hover:text-primary hover:underline">{i.title}</AppLink>
                <div className="font-mono text-[11.5px] text-muted-foreground">{i.incident_id} · {i.asset_id}</div>
              </td>
              <td><StatusBadge status={i.status} /></td>
              <td><RiskBadge level={i.risk_level} /></td>
              {!compact && <>
                <td><Badge>{SCORE_KIND_LABEL[i.score_kind]}</Badge></td>
                <td><Mono>{i.detector_id}</Mono></td>
                <td><OriginBadge origin={i.data_origin} /></td>
                <td className="text-right"><Mono>{i.prediction_count}</Mono></td>
              </>}
              <td className="whitespace-nowrap"><Mono>{dt(i.opened_at)}</Mono></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
