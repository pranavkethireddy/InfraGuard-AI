import { useQuery } from "@tanstack/react-query";
import { ApiError } from "@/api/client";
import { assetQuery, modelsQuery, readingsQuery } from "@/api/queries";
import type { Reading } from "@/api/types";
import { AppLink } from "@/lib/router-adapter";
import { serverPath } from '@/api/parts-types';
import { ReadingsChart } from "@/components/ReadingsChart";
import { Badge, Empty, ErrorState, Fields, Loading, Mono, OriginBadge, PageHeader, RiskBadge, Section, SourceDetails, dt, money, val } from "@/components/ui-kit";

export function NotFoundState({ what, back, backLabel }: { what: string; back: string; backLabel: string }) {
  return (
    <div className="border border-border bg-card p-6">
      <p className="font-semibold text-foreground">{what} not found</p>
      <AppLink to={back} className="mt-2 inline-block text-[13px] text-primary underline underline-offset-2">{backLabel}</AppLink>
    </div>
  );
}

export function ReadingsTable({ readings }: { readings: Reading[] }) {
  const fields = Array.from(new Set(readings.flatMap((r) => Object.keys(r.values))));
  return (
    <div className="overflow-x-auto">
      <table className="data-table">
        <caption className="sr-only">Reading history</caption>
        <thead><tr><th>Observed (UTC)</th>{fields.map((f) => <th key={f} className="text-right">{f}</th>)}<th>Data</th></tr></thead>
        <tbody className="font-mono text-[12.5px]">
          {readings.map((r) => (
            <tr key={r.observed_at}><td>{dt(r.observed_at)}</td>{fields.map((f) => <td key={f} className="text-right">{val(r.values[f])}</td>)}<td className="font-sans"><OriginBadge origin={r.data_origin} /></td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function AssetDetailPage({ id }: { id: string }) {
  const asset = useQuery(assetQuery(id));
  const readings = useQuery(readingsQuery(id));
  const models = useQuery(modelsQuery());
  if (asset.isLoading) return <Loading />;
  if (asset.error instanceof ApiError && asset.error.status === 404) return <NotFoundState what={`Asset "${id}"`} back="/assets" backLabel="Back to assets" />;
  if (asset.error || !asset.data) return <ErrorState error={asset.error} />;
  const a = asset.data;
  const detector = models.data?.items.find((m) => m.detector_id === a.compatible_detector);
  const threshold = detector?.rule_config?.temperature_threshold_c ?? null;
  const ia = a.impact_assumptions;
  return (
    <>
      <PageHeader title={a.name} meta={<>{a.asset_id} · {a.asset_type} · {a.location}</>}
        actions={<><RiskBadge level={a.current_risk_level} /><OriginBadge origin={a.data_origin} /></>} />
      {a.asset_type === 'gpu_server' && <AppLink to={serverPath(id)} className="mb-5 inline-block text-primary underline">Server / GPU detail →</AppLink>}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-6">
          <Section title="Temperature trend" aside={readings.data && <Mono>{readings.data.total} readings · limit {readings.data.limit}</Mono>}>
            {readings.isLoading ? <Loading /> : readings.error ? <ErrorState error={readings.error} />
              : readings.data?.items.length ? <ReadingsChart readings={readings.data.items} threshold={threshold} /> : <Empty>No readings in the returned window.</Empty>}
          </Section>
          <Section title="Reading history" aside={readings.data && <Mono>{dt(readings.data.start)} → {dt(readings.data.end)}</Mono>} flush>
            {readings.data?.items.length ? <ReadingsTable readings={readings.data.items} /> : readings.isLoading ? <Loading /> : <Empty>No readings.</Empty>}
          </Section>
        </div>
        <div className="min-w-0 space-y-6">
          <Section title="Asset">
            <Fields rows={[
              ["Type", <Mono>{a.asset_type}</Mono>],
              ["Criticality", <span className="capitalize">{a.criticality}</span>],
              ["Detector", <Mono>{a.compatible_detector ?? "None"}</Mono>],
              ["Last reading", <Mono>{dt(a.last_reading_at)}</Mono>],
              ["Active incident", a.active_incident_id
                ? <AppLink to={`/incidents/${a.active_incident_id}`} className="font-mono text-[12.5px] text-primary underline underline-offset-2">{a.active_incident_id}</AppLink> : "None"],
            ]} />
          </Section>
          <Section title="Impact assumptions" aside={<Badge>Read-only</Badge>}>
            {ia ? (
              <>
                <Fields rows={[
                  ["Currency", <Mono>{ia.currency}</Mono>],
                  ["Downtime", <Mono>{val(ia.estimated_downtime_hours)} h</Mono>],
                  ["Cost per hour", <Mono>{money(ia.cost_per_hour, ia.currency)}</Mono>],
                  ["Repair cost", <Mono>{money(ia.estimated_repair_cost, ia.currency)}</Mono>],
                ]} />
                <div className="mt-2 border-t border-border pt-2"><SourceDetails><p>assumptions_source: {ia.assumptions_source ?? "Not reported"}</p><p>Scenario estimates; not measured costs or actual billing.</p></SourceDetails></div>
                <p className="mt-1 text-xs text-muted-foreground">Editing assumptions is not yet available.</p>
              </>
            ) : <Empty>No impact assumptions provided.</Empty>}
          </Section>
        </div>
      </div>
    </>
  );
}
