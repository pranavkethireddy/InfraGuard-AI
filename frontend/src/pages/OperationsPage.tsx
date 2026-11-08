import { useState } from 'react';
import { useIsMutating, useQuery } from '@tanstack/react-query';
import type { SiteId } from '@/api/fleet-types';
import { learningCasesQuery, learningMatrixQuery, planQuery } from '@/api/ops-queries';
import { useCrewStream } from '@/api/ops-stream';
import { AutoDispatch } from '@/components/AutoDispatch';
import { StreamStatus } from '@/components/StreamStatus';
import { PriorityRank } from '@/components/PriorityRank';
import { AppLink } from '@/lib/router-adapter';
import { DispatchControl, available } from '@/components/OperationsWorkspace';
import { Badge, ConsoleButton, Empty, ErrorState, Loading, Mono, PageHeader, Section, SourceDetails, inputCls } from '@/components/ui-kit';

export function OperationsPage({ site, onSiteChange }: { site: SiteId; onSiteChange: (site: SiteId) => void }) {
  return <><PageHeader title="Operations" meta="Backend-ranked repair plan · human review required" />
    <div role="tablist" aria-label="Operations site" className="mb-6 flex flex-wrap gap-2">
      {(['datacenter', 'mining'] as const).map((s) => <ConsoleButton key={s} role="tab" aria-selected={site === s} variant={site === s ? 'primary' : 'outline'} onClick={() => onSiteChange(s)}>{s === 'mining' ? 'Crypto mining site' : 'Data center'}</ConsoleButton>)}
    </div><OperationsSite key={site} site={site} /></>;
}
function OperationsSite({ site }: { site: SiteId }) {
  const crew = useCrewStream(site);
  const plan = useQuery(planQuery(site));
  const matrix = useQuery(learningMatrixQuery());
  const [assetType, setAssetType] = useState('');
  const cases = useQuery(learningCasesQuery(site, assetType || undefined));
  const pending = useIsMutating({ mutationKey: ['ops', 'dispatch'] }) > 0;
  return <div className="space-y-6">
    <Section title="Automatic dispatch"><AutoDispatch enabled={crew.data?.auto_dispatch} /><div className="mt-3"><StreamStatus stream={crew.stream} /></div></Section>
    <Section title="Repair plan" aside={<Badge>Backend ranking</Badge>}>
      {plan.isLoading ? <Loading /> : !plan.data ? <ErrorState error={plan.error} /> : <>
        {plan.error && <ErrorState error={plan.error} />}<p className="mb-3 text-xs text-muted-foreground">DEMO clock {plan.data.demo_time} · total savings {plan.data.total_savings} USD</p><SourceDetails><p>assumptions_source: {plan.data.assumptions_source}</p><p>Scenario repair/revenue estimates; not actual billing.</p></SourceDetails>
        {plan.data.items.length ? <div className="max-w-full min-w-0 overflow-x-auto"><table className="data-table"><thead><tr><th>Priority rank</th><th>Incident / action</th><th>Recommendation</th><th>Technician / move from</th><th>Savings / DEMO repair h</th><th>Savings per tech hour</th><th>Status</th><th>Dispatch</th></tr></thead><tbody>
          {plan.data.items.map((p) => <tr key={p.incident_id}><td><PriorityRank incidentId={p.incident_id} /></td><td><AppLink to={`/incidents/${p.incident_id}`} className="text-primary underline">{p.title}</AppLink><p>{p.action}</p><Mono>{p.asset_id}</Mono></td><td>{available(p.recommended_option)}</td><td>{available(p.technician_name)}<p>{p.move_from ?? 'No displaced job'}</p></td><td>{available(p.savings)} USD / {available(p.repair_hours)} DEMO h</td><td>{available(p.savings_per_tech_hour)} USD/h</td><td>{p.status}<p><Mono>{p.work_order_id}</Mono></p></td><td>{p.recommended_option ? <DispatchControl incidentId={p.incident_id} option={p.recommended_option} disabled={p.status !== 'ready' || !!p.work_order_id || pending || plan.isFetching || !!plan.error} /> : 'Unavailable'}</td></tr>)}
        </tbody></table></div> : <Empty>No repair plan items.</Empty>}
      </>}
    </Section>
    <Section title="Crew">
      {crew.isLoading ? <Loading /> : !crew.data ? <ErrorState error={crew.error} /> : <>
        {crew.error && <ErrorState error={crew.error} />}<p className="mb-3 text-xs text-muted-foreground">{crew.data.demo_time} · {crew.data.demo_minutes_per_tick} DEMO minutes/tick · {crew.data.walk_cells_per_demo_minute ?? 'Not reported'} cells/DEMO minute</p><SourceDetails><p>Fictional demo crew; prototype repair workflow.</p><p>assumptions_source: {crew.data.assumptions_source}</p></SourceDetails>
        {crew.data.technicians.length ? <div className="max-w-full min-w-0 overflow-x-auto"><table className="data-table"><thead><tr><th>Technician / skills</th><th>Status / location</th><th>Current work order</th><th>Travel / progress / ETA</th><th>Queue — backend order / rank</th></tr></thead><tbody>{crew.data.technicians.map((t) => <tr key={t.technician_id}><td>{t.name}<p className="text-xs text-muted-foreground">{t.role} · {t.skills.join(', ')}</p><Mono>{t.technician_id} · {t.rate_per_hour} USD/h</Mono></td><td>{t.status}<p>{t.location_hall_id}</p></td><td>{t.current_work_order?.title ?? 'None'}<p><Mono>{t.current_work_order?.work_order_id}</Mono></p>{t.current_work_order && <p>Priority rank: <PriorityRank incidentId={t.current_work_order.incident_id} /></p>}</td><td>{t.current_work_order ? <>{t.current_work_order.status}<p>{t.current_work_order.hours_done} / {t.current_work_order.hours_total} DEMO h</p><p>Progress (fraction): {t.current_work_order.progress}</p><p>{available(t.current_work_order.eta_minutes)} DEMO minutes</p></> : 'No active work'}</td><td>{t.queued_work_order_ids.length ? <ol>{t.queued_work_order_ids.map((id) => { const w = crew.data?.work_orders.find((order) => order.work_order_id === id); return <li key={id}><Mono>{id}</Mono><p>{w?.title ?? 'Work order not reported'}</p><p>{w?.status ?? 'Status not reported'} · Priority rank: <PriorityRank incidentId={w?.incident_id} /></p></li>; })}</ol> : 'None'}</td></tr>)}</tbody></table></div> : <Empty>No technicians returned for this site.</Empty>}
        <details className="mt-4 border-t border-border pt-3"><summary className="cursor-pointer text-sm">Site work orders</summary>{crew.data.work_orders.length ? <div className="max-w-full min-w-0 overflow-x-auto"><table className="data-table"><thead><tr><th>Work order</th><th>Priority rank</th><th>Status</th><th>ETA / progress</th></tr></thead><tbody>{crew.data.work_orders.map((w) => <tr key={w.work_order_id}><td>{w.title}<p><Mono>{w.work_order_id}</Mono></p></td><td><PriorityRank incidentId={w.incident_id} /></td><td>{w.status}</td><td>{available(w.eta_minutes)} DEMO minutes · {w.progress} fraction</td></tr>)}</tbody></table></div> : <Empty>No work orders.</Empty>}</details>
      </>}
    </Section>
    <Section title="Learning matrix" aside={<Badge>Read-only · shared across sites</Badge>}>
      {matrix.isLoading ? <Loading /> : !matrix.data ? <ErrorState error={matrix.error} /> : <>
        {matrix.error && <ErrorState error={matrix.error} />}<p className="mb-3 text-xs text-muted-foreground">{matrix.data.total_cases} returned cases · averages and outcomes as returned; not model evaluation</p>
        {matrix.data.rows.length ? <div className="max-w-full min-w-0 overflow-x-auto"><table className="data-table"><thead><tr><th>Asset / symptom</th><th>Cases / sites / shared with</th><th>Average repair</th><th>Average cost</th><th>Fixed before failure</th><th>Best fix / last learned</th></tr></thead><tbody>{matrix.data.rows.map((r, n) => <tr key={n}><td>{r.asset_type}<p>{r.symptom}</p></td><td>{r.cases}<p>{r.sites_seen.join(', ')}</p><p>Shared: {r.shared_with_sites.join(', ')}</p></td><td>{available(r.avg_repair_hours)} DEMO h</td><td>{available(r.avg_cost)} USD</td><td>{available(r.fixed_before_failure_pct)} %</td><td>{available(r.best_fix)}<p><Mono>{r.last_learned_at}</Mono></p></td></tr>)}</tbody></table></div> : <Empty>No learned cases. No outcomes or averages available.</Empty>}
      </>}
    </Section>
    <Section title="Learning cases" aside={<label className="flex flex-wrap items-center gap-2">Asset type<input aria-label="Learning asset type" className={inputCls} value={assetType} onChange={(e) => setAssetType(e.target.value)} placeholder="All types" /></label>}>
      {cases.isLoading ? <Loading /> : !cases.data ? <ErrorState error={cases.error} /> : <>
        {cases.error && <ErrorState error={cases.error} />}{cases.data.items.length ? <div className="max-w-full min-w-0 overflow-x-auto"><table className="data-table"><thead><tr><th>Case / asset / site</th><th>Symptom / cause</th><th>Fix</th><th>Outcome / source</th><th>Repair / cost / learned</th></tr></thead><tbody>{cases.data.items.map((c) => <tr key={c.case_id}><td><Mono>{c.case_id}</Mono><p>{c.asset_id} · {c.asset_type} · {c.site_id}</p></td><td>{c.symptom}<p>{available(c.cause)}</p></td><td>{c.fix}</td><td>{c.outcome}<SourceDetails><p>Source: {c.source}</p></SourceDetails></td><td>{c.repair_hours} DEMO h · {c.cost} USD<p><Mono>{c.learned_at}</Mono></p></td></tr>)}</tbody></table></div> : <Empty>No learned cases for this site and asset type.</Empty>}
      </>}
    </Section>
  </div>;
}