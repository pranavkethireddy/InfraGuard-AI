import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError, DATA_MODE, FIXTURE_MUTATION_MESSAGE } from "@/api/client";
import { incidentQuery, modelsQuery, readingsQuery, usePatchIncident } from "@/api/queries";
import type { Impact, IncidentStatus } from "@/api/types";
import { AppLink } from "@/lib/router-adapter";
import { ReadingsChart } from "@/components/ReadingsChart";
import { NotFoundState } from "./AssetDetailPage";
import {
  Badge, Empty, ErrorMessage, ErrorState, Fields, Loading, Mono, OriginBadge, PageHeader, RiskBadge, ScoreValue, Section,
  StatusBadge, btnOutline, btnPrimary, dt, inputCls, money, val,
} from "@/components/ui-kit";

/** Allowed transitions per contract: open -> acknowledged|resolved, acknowledged -> resolved. */
export function allowedTransitions(s: IncidentStatus): ("acknowledged" | "resolved")[] {
  if (s === "open") return ["acknowledged", "resolved"];
  if (s === "acknowledged") return ["resolved"];
  return [];
}

/** Impact ledger: every line is a value returned by the API; nothing is summed in the browser. */
export function ImpactLedger({ impact: im }: { impact: Impact }) {
  const c = im.currency;
  return (
    <div>
      <table className="data-table">
        <caption className="sr-only">Impact ledger</caption>
        <tbody className="font-mono text-[12.5px]">
          <tr><td className="font-sans text-muted-foreground">Estimated downtime</td><td className="text-right">{val(im.estimated_downtime_hours)} h</td></tr>
          <tr><td className="font-sans text-muted-foreground">Cost per hour</td><td className="text-right">{money(im.cost_per_hour, c)}</td></tr>
          <tr><td className="font-sans text-muted-foreground">Downtime cost</td><td className="text-right">{money(im.estimated_downtime_cost, c)}</td></tr>
          <tr><td className="font-sans text-muted-foreground">Repair cost</td><td className="text-right">{money(im.estimated_repair_cost, c)}</td></tr>
          <tr className="border-t-2 border-rule-strong">
            <td className="font-sans font-semibold text-foreground">Estimated total impact</td>
            <td className="text-right text-[15px] font-semibold text-foreground">{money(im.estimated_total_impact, c)}</td>
          </tr>
        </tbody>
      </table>
      <p className="mt-2 px-3 text-xs text-muted-foreground">Figures as returned by the API ({c}). Estimates, not measured losses.</p>
      {im.assumptions_source && <p className="mt-1 px-3 text-xs text-attention-foreground">Source: {im.assumptions_source}</p>}
    </div>
  );
}

export function IncidentDetailPage({ id }: { id: string }) {
  const q = useQuery(incidentQuery(id));
  const assetId = q.data?.asset_id ?? "";
  const readings = useQuery({ ...readingsQuery(assetId), enabled: !!assetId });
  const models = useQuery(modelsQuery());
  const patch = usePatchIncident(id);
  const [note, setNote] = useState("");
  if (q.isLoading) return <Loading />;
  if (q.error instanceof ApiError && q.error.status === 404) return <NotFoundState what={`Incident "${id}"`} back="/incidents" backLabel="Back to incidents" />;
  if (q.error || !q.data) return <ErrorState error={q.error} />;
  const i = q.data;
  const p = i.latest_prediction;
  const transitions = allowedTransitions(i.status);
  const fixture = DATA_MODE === "fixture";
  const threshold = models.data?.items.find((m) => m.detector_id === i.detector_id)?.rule_config?.temperature_threshold_c ?? null;

  return (
    <>
      <PageHeader title={i.title}
        meta={<>{i.incident_id} · asset <AppLink to={`/assets/${i.asset_id}`} className="text-primary underline underline-offset-2">{i.asset_id}</AppLink> · {i.detector_id}{i.simulation_id ? ` · ${i.simulation_id}` : ""}</>}
        actions={<><StatusBadge status={i.status} /><RiskBadge level={i.risk_level} /><OriginBadge origin={i.data_origin} /></>} />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(20rem,1fr)]">
        {/* Investigation: evidence */}
        <div className="space-y-4">
          <Section title="Rule evidence" flush>
            {i.evidence.length ? (
              <div className="overflow-x-auto">
                <table className="data-table">
                  <caption className="sr-only">Evidence</caption>
                  <thead><tr><th>Type</th><th>Field</th><th className="text-right">Value</th><th className="text-right">Threshold</th><th className="text-right">Consecutive readings</th></tr></thead>
                  <tbody className="font-mono text-[12.5px]">
                    {i.evidence.map((e, k) => (
                      <tr key={k}><td>{e.type}</td><td>{e.field}</td><td className="text-right">{val(e.value)} {e.unit}</td><td className="text-right">{val(e.threshold)} {e.unit}</td><td className="text-right">{val(e.consecutive_readings)}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <Empty>No evidence recorded.</Empty>}
          </Section>

          <Section title={`Sensor trend — ${i.asset_id}`} aside={readings.data && <Mono>{readings.data.total} readings</Mono>}>
            {readings.isLoading ? <Loading /> : readings.error ? <ErrorState error={readings.error} />
              : readings.data?.items.length ? <ReadingsChart readings={readings.data.items} threshold={threshold} height={200} /> : <Empty>No readings returned.</Empty>}
          </Section>

          <Section title="Explanation" aside={i.explanation_source && <Badge>source: {i.explanation_source}</Badge>}>
            {i.explanation ? <p className="max-w-prose text-[13.5px] leading-relaxed">{i.explanation}</p> : <Empty>No explanation provided.</Empty>}
          </Section>

          <Section title="Maintenance records" flush>
            {i.maintenance_sources.length ? (
              <table className="data-table">
                <caption className="sr-only">Maintenance records</caption>
                <thead><tr><th>Record</th><th>Recorded</th><th>Excerpt</th><th className="text-right">Retrieval score</th></tr></thead>
                <tbody>
                  {i.maintenance_sources.map((m) => (
                    <tr key={m.record_id}>
                      <td><Mono>{m.record_id}</Mono><div className="text-[11.5px] text-muted-foreground">{m.source_name}</div></td>
                      <td className="whitespace-nowrap"><Mono>{dt(m.recorded_at)}</Mono></td>
                      <td>{m.excerpt}</td>
                      <td className="text-right"><Mono>{val(m.score)}</Mono></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <Empty>No maintenance records linked.</Empty>}
          </Section>

          <Section title="Latest prediction">
            {p ? (
              <div className="space-y-2">
                <ScoreValue score={p.risk_score} kind={p.score_kind} />
                <Fields rows={[
                  ["Prediction", <Mono>{p.prediction_id}</Mono>],
                  ["Model", <Mono>{p.model_name} v{p.model_version}</Mono>],
                  ["Target", p.target],
                  ["Horizon", p.prediction_horizon_hours == null ? "None (not a forecast)" : <Mono>{p.prediction_horizon_hours} h</Mono>],
                  ["Observed", <Mono>{dt(p.observed_at)}</Mono>],
                  ["Generated", <Mono>{dt(p.generated_at)}</Mono>],
                ]} />
                {p.limitations.length > 0 && <ul className="list-disc border-t border-border pl-5 pt-2 text-xs text-muted-foreground">{p.limitations.map((l) => <li key={l}>{l}</li>)}</ul>}
              </div>
            ) : <Empty>No prediction attached.</Empty>}
          </Section>
        </div>

        {/* Ledger + actions */}
        <div className="space-y-4">
          <Section title="Impact ledger" flush>
            {i.impact ? <div className="pb-3"><ImpactLedger impact={i.impact} /></div> : <Empty>No impact estimate.</Empty>}
          </Section>

          <Section title="Priority">
            <p className="font-mono text-base font-semibold">{val(i.priority_index)}</p>
            <p className="text-xs text-muted-foreground">Priority index calculated by the backend.</p>
            {i.priority_weights && (
              <table className="data-table mt-2">
                <caption className="eyebrow mb-1 text-left">Weights</caption>
                <tbody className="font-mono text-[12.5px]">{Object.entries(i.priority_weights).map(([k, v]) => <tr key={k}><td>{k}</td><td className="text-right">{v}</td></tr>)}</tbody>
              </table>
            )}
          </Section>

          <Section title="Recommended actions">
            {i.recommended_actions.length ? <ol className="list-decimal space-y-1 pl-5 text-[13px]">{i.recommended_actions.map((a) => <li key={a}>{a}</li>)}</ol> : <Empty>None provided.</Empty>}
          </Section>

          <Section title="Status">
            {transitions.length === 0 ? <p className="text-[13px] text-muted-foreground">Resolved — no further transitions.</p> : (
              <form onSubmit={(e) => e.preventDefault()} className="space-y-2">
                <label className="block text-[13px]">
                  <span className="text-muted-foreground">Note (optional)</span>
                  <textarea className={`${inputCls} mt-1`} rows={2} value={note} onChange={(e) => setNote(e.target.value)} disabled={fixture} />
                </label>
                <div className="flex flex-wrap gap-2">
                  {transitions.map((t) => (
                    <button key={t} type="button" disabled={fixture || patch.isPending}
                      className={t === "resolved" ? btnPrimary : btnOutline}
                      onClick={() => { if (!fixture) patch.mutate({ status: t, note: note.trim() || null }, { onSuccess: () => setNote("") }); }}>
                      Mark {t}
                    </button>
                  ))}
                </div>
                {fixture && <p className="text-xs text-muted-foreground">{FIXTURE_MUTATION_MESSAGE}</p>}
                {patch.error && <div role="alert" className="border-l-2 border-destructive pl-2"><ErrorMessage error={patch.error} /></div>}
              </form>
            )}
          </Section>

          <Section title="Timeline">
            <Fields rows={[
              ["Opened", <Mono>{dt(i.opened_at)}</Mono>],
              ["Last seen", <Mono>{dt(i.last_seen_at)}</Mono>],
              ["Acknowledged", <Mono>{dt(i.acknowledged_at)}</Mono>],
              ["Resolved", <Mono>{dt(i.resolved_at)}{i.resolved_by ? ` · ${i.resolved_by}` : ""}</Mono>],
              ["Predictions", <Mono>{i.prediction_count}</Mono>],
            ]} />
            <div className="mt-2 border-t border-border pt-2">
              <p className="eyebrow">Notes</p>
              {i.notes.length ? (
                <ul className="mt-1 space-y-1.5 text-[13px]">
                  {i.notes.map((n, k) => <li key={k}><Mono>{dt(n.created_at)} · {n.status}</Mono><p>{n.note}</p></li>)}
                </ul>
              ) : <p className="mt-1 text-[13px] text-muted-foreground">No notes.</p>}
            </div>
          </Section>
        </div>
      </div>
    </>
  );
}
