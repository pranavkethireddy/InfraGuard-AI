import { useEffect, useState } from 'react';
import { useIsMutating, useQuery, useQueryClient } from '@tanstack/react-query';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Send, LoaderCircle } from 'lucide-react';
import { ApiError, DATA_MODE, FIXTURE_MUTATION_MESSAGE } from '@/api/client';
import { learningCasesQuery, techniciansQuery, useDispatch, whatIfQuery } from '@/api/ops-queries';
import type { DispatchResponse, RepairOption, WhatIfResponse } from '@/api/ops-types';
import type { SiteId } from '@/api/fleet-types';
import { Badge, ConsoleButton, Empty, ErrorMessage, ErrorState, Fields, Loading, Mono, Section, SourceDetails, inputCls, val } from './ui-kit';

export const available = (v: unknown) => v == null ? 'Unavailable' : String(v);
const colors = ['var(--primary)', 'var(--chart-line)', 'var(--attention)'];
export function WhatIfCurves({ data }: { data: WhatIfResponse }) {
  return <div>
    <p className="mb-3 text-xs text-muted-foreground">{available(data.metric)} · {available(data.unit)} · DEMO hours · power states as returned</p>
    {data.options.some((o) => o.curve?.some((p) => p.value != null)) && data.metric && data.unit ?
      <div className="h-80 w-full" role="img" aria-label={`What-if curves: ${data.metric} (${data.unit}), DEMO hours`}>
        <ResponsiveContainer width="100%" height="100%"><LineChart margin={{ top: 10, right: 20, bottom: 24, left: 10 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
          <XAxis type="number" dataKey="hour" domain={['dataMin', 'dataMax']} stroke="var(--muted-foreground)" label={{ value: 'DEMO hours', position: 'insideBottom', offset: -15, fill: 'var(--muted-foreground)' }} />
          <YAxis type="number" stroke="var(--muted-foreground)" label={{ value: data.unit, angle: -90, position: 'insideLeft', fill: 'var(--muted-foreground)' }} />
          <Tooltip content={({ active, payload }) => active && payload?.length ? <div className="rounded-sm border border-border bg-popover p-3 text-xs">{payload.map((p, index) => <p key={`${String(p.name)}-${index}`}>{p.name}: {available(p.value)} {data.unit} · {p.payload.hour} DEMO h · power {available(p.payload.power_state)}</p>)}</div> : null} />
          <Legend verticalAlign="top" />
          {data.options.map((o, n) => <Line key={o.option} data={o.curve ?? []} name={o.label} type="linear" dataKey="value" stroke={colors[n % colors.length]} dot={false} connectNulls={false} isAnimationActive={false} />)}
        </LineChart></ResponsiveContainer>
      </div> : <Empty>Curves unavailable — no failure-time or no-risk inference.</Empty>}
    {data.options.map((o) => <details key={o.option} className="border-t border-border py-2"><summary className="cursor-pointer text-xs">{o.label} · curve points and power states</summary>
      {o.curve?.length ? <div className="max-w-full min-w-0 overflow-x-auto"><table className="data-table"><thead><tr><th>DEMO hour</th><th>{available(data.metric)} ({available(data.unit)})</th><th>Power</th></tr></thead><tbody>{o.curve.map((p, k) => <tr key={k}><td>{p.hour}</td><td>{available(p.value)}</td><td>{p.power_state}</td></tr>)}</tbody></table></div> : <Empty>Curve unavailable.</Empty>}
    </details>)}
  </div>;
}
export function DispatchResult({ result }: { result: DispatchResponse }) {
  const w = result.work_order;
  return <div role="status" className="mt-3 border-l-2 border-healthy pl-3"><p className="text-xs text-muted-foreground">Initial dispatch result — snapshot, not current progress</p><p className="font-semibold">Dispatched · {w.work_order_id}</p>
    <Fields rows={[["Work order", w.title], ["Technician", result.technician.name], ["Status", w.status], ["Progress (fraction)", val(w.progress)], ["ETA", `${available(w.eta_minutes)} DEMO minutes`], ["Displaced job", result.displaced?.title ?? 'None reported']]} />
  </div>;
}
export function DispatchControl({ incidentId, option, disabled = false, technicianId }: { incidentId: string; option: RepairOption; disabled?: boolean; technicianId?: string | undefined }) {
  const action = useDispatch();
  const pending = useIsMutating({ mutationKey: ['ops', 'dispatch'] }) > 0;
  const fixture = DATA_MODE === 'fixture';
  const terminalConflict = action.error instanceof ApiError && (action.error.code === 'ALREADY_DISPATCHED' || action.error.code === 'INCIDENT_RESOLVED');
  const locked = fixture || disabled || pending || action.isSuccess || terminalConflict;
  return <div><ConsoleButton variant="primary" disabled={locked} aria-busy={action.isPending}
    onClick={() => { if (!locked) action.mutate({ incident_id: incidentId, option, ...(technicianId ? { technician_id: technicianId } : {}) }); }}>
    {action.isPending ? <LoaderCircle className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Send className="h-4 w-4" aria-hidden />}
    {action.isPending ? 'Dispatching…' : terminalConflict ? 'Dispatch unavailable' : action.error ? 'Retry dispatch' : 'Dispatch'}
  </ConsoleButton>{fixture && <p className="mt-2 text-xs text-muted-foreground">{FIXTURE_MUTATION_MESSAGE}</p>}
    {action.error && <div role="alert" className="mt-2"><ErrorMessage error={action.error} /><p className="text-xs text-muted-foreground">State refreshed. Review availability before retrying; no automatic dispatch.</p></div>}
    {action.data && <DispatchResult result={action.data} />}
  </div>;
}
export function IncidentWhatIf({ id, resolved, workOrderId }: { id: string; resolved: boolean; workOrderId?: string | null | undefined }) {
  return <WhatIfWorkspace key={id} id={id} resolved={resolved} workOrderId={workOrderId} />;
}
function WhatIfWorkspace({ id, resolved, workOrderId }: { id: string; resolved: boolean; workOrderId?: string | null | undefined }) {
  const q = useQuery(whatIfQuery(id));
  const site: SiteId = q.data?.site_id === 'mining' ? 'mining' : 'datacenter';
  const crew = useQuery({ ...techniciansQuery(site), enabled: !!q.data });
  const learned = useQuery({ ...learningCasesQuery(site), enabled: resolved && !!q.data });
  const qc = useQueryClient();
  useEffect(() => {
    if (resolved) {
      for (const key of ['learning', 'incidents', 'assets', 'fleet', 'ops']) void qc.invalidateQueries({ queryKey: [key] });
    }
  }, [resolved, id, qc]);
  const [technician, setTechnician] = useState('');
  const assigned = crew.data?.work_orders.find((w) => workOrderId ? w.work_order_id === workOrderId : w.incident_id === id);
  const alreadyDispatched = !resolved && assigned?.status !== 'done' && (!!assigned || !!workOrderId);
  return <Section title="What-if" aside="Human review required">
    {q.isLoading ? <Loading /> : !q.data ? <ErrorState error={q.error} /> : <div className="space-y-5">
      {q.error && <ErrorState error={q.error} />}
      <p className="text-xs text-muted-foreground">DEMO clock {q.data.demo_time}</p><SourceDetails><p>assumptions_source: {q.data.assumptions_source}</p><p>Prototype scenario repair/revenue estimates; not production observations or actual billing.</p></SourceDetails>
      <p><strong>Backend recommendation: </strong>{available(q.data.recommended)} · {q.data.reason}</p>
      <Fields rows={[["Current value", `${available(q.data.current_value)} ${available(q.data.unit)}`], ["Trend per DEMO hour", available(q.data.trend_per_hour)], ["Shutdown threshold", available(q.data.shutdown_threshold)], ["Shutdown in DEMO hours", available(q.data.shutdown_in_hours)], ["Window", `${q.data.window.label}: ${q.data.window.starts_in_hours}–${q.data.window.ends_in_hours} DEMO h`], ["Breakeven USD/MWh", available(q.data.window.breakeven_usd_per_mwh)], ["Savings vs worst (USD)", available(q.data.savings_vs_worst)]]} />
      <WhatIfCurves data={q.data} />
      {crew.error && <ErrorState error={crew.error} />}
      {(assigned || workOrderId) && <div role="region" aria-label="Assigned work order" className="border-t border-border py-4">
        <h3 className="mb-3 font-semibold">Assigned work order · current backend state</h3>
        {assigned ? <>
          <Fields rows={[["Work order", assigned.work_order_id], ["Title", assigned.title], ["Technician", crew.data?.technicians.find((t) => t.technician_id === assigned.technician_id)?.name ?? assigned.technician_id], ["Status", assigned.status], ["Progress (fraction)", assigned.progress], ["ETA", `${available(assigned.eta_minutes)} DEMO minutes`], ["Completed at", available(assigned.completed_at)]]} />
          {assigned.cost && <div className="max-w-full min-w-0 overflow-x-auto"><table className="data-table mt-3"><caption className="text-left text-xs">Completed work-order cost · USD</caption><tbody>{Object.entries(assigned.cost).map(([key, value]) => <tr key={key}><td>{key}</td><td>{value}</td></tr>)}</tbody></table></div>}
        </> : <p>{crew.isLoading ? 'Loading assigned work order…' : 'Assigned work-order status unavailable.'}</p>}
      </div>}
      {resolved && <div role="region" aria-label="Repair learning result" className="border-t border-border py-4">
        <h3 className="mb-3 font-semibold">Returned learning result</h3>
        {learned.isLoading ? <Loading /> : learned.error ? <ErrorState error={learned.error} /> : learned.data?.items.some((c) => c.asset_id === q.data?.asset_id) ?
          <div className="max-w-full min-w-0 overflow-x-auto"><table className="data-table"><thead><tr><th>Case</th><th>Outcome / source</th><th>Fix</th><th>Repair / cost</th></tr></thead><tbody>{learned.data.items.filter((c) => c.asset_id === q.data?.asset_id).map((c) => <tr key={c.case_id}><td>{c.case_id}</td><td>{c.outcome}<SourceDetails><p>Source: {c.source}</p></SourceDetails></td><td>{c.fix}</td><td>{c.repair_hours} DEMO h · {c.cost} USD</td></tr>)}</tbody></table></div> : <Empty>No learned result returned for this asset.</Empty>}
      </div>}
      <label className="block max-w-sm text-xs">Technician (optional explicit choice)<select className={`${inputCls} mt-1`} value={technician} onChange={(e) => setTechnician(e.target.value)} disabled={DATA_MODE === 'fixture' || crew.isLoading || !!crew.error}>
        <option value="">Backend selection</option>{crew.data?.technicians.map((t) => <option key={t.technician_id} value={t.technician_id}>{t.name} · {t.role} · {t.status}</option>)}
      </select></label>
      {resolved && <p>Resolved — dispatch unavailable.</p>}{alreadyDispatched && <p>Already dispatched — active work order.</p>}
      <div className="divide-y divide-border">{q.data.options.map((o) => <article key={o.option} className="py-5">
        <h3 className="mb-2 font-semibold">{o.label} {o.option === q.data?.recommended && <Badge tone="accent">Backend recommended</Badge>}</h3><p className="mb-3 text-sm">{o.description}</p>
        <Fields rows={[["Technician", o.technician_name ?? 'Unavailable'], ["Displaced job", o.displaces ?? 'None reported'], ["Start / done", `${available(o.start_in_hours)} / ${available(o.done_in_hours)} DEMO h`], ["Shutdown / downtime", `${available(o.shutdown_at_hours)} / ${available(o.downtime_hours)} DEMO h`]]} />
        <div className="max-w-full min-w-0 overflow-x-auto"><table className="data-table my-3"><caption className="text-left text-xs text-muted-foreground">Itemized costs · USD</caption><tbody>{Object.entries(o.costs).map(([k, v]) => <tr key={k}><td>{k.replaceAll('_', ' ')}</td><td><Mono>{available(v)}</Mono></td></tr>)}</tbody></table></div>
        {o.risk_note && <p className="mb-3 text-attention-foreground">{o.risk_note}</p>}
        <DispatchControl incidentId={id} option={o.option} technicianId={technician || undefined} disabled={resolved || !!alreadyDispatched || crew.isFetching || !!crew.error || q.isFetching} />
      </article>)}</div>
    </div>}
  </Section>;
}