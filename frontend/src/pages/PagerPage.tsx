import { useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { LoaderCircle } from 'lucide-react';
import { api, DATA_MODE, FIXTURE_MUTATION_MESSAGE, ApiError } from '@/api/client';
import { isPagerView, newerPager, pagerKey, usePagerStream } from '@/api/ops-stream';
import type { PagerView } from '@/api/ops-types';
import { AppLink } from '@/lib/router-adapter';
import { PriorityRank } from '@/components/PriorityRank';
import { StreamStatus } from '@/components/StreamStatus';
import { Badge, ConsoleButton, Empty, ErrorState, Fields, Loading, PageHeader, Section, SourceDetails, inputCls } from '@/components/ui-kit';

export function PagerPage({ technicianId = 'tech-03', onTechnicianChange }: { technicianId?: string; onTechnicianChange: (id: string) => void }) {
  return <PagerWorkspace key={technicianId} id={technicianId} onTechnicianChange={onTechnicianChange} />;
}
function PagerWorkspace({ id, onTechnicianChange }: { id: string; onTechnicianChange: (id: string) => void }) {
  const pager = usePagerStream(id);
  const qc = useQueryClient();
  const lock = useRef(false);
  const mutation = useMutation({ mutationKey: ['pager', id], retry: false,
    mutationFn: async ({ command, order }: { command: 'claim' | 'release' | 'done'; order?: string }) => {
      if (command !== 'claim' && command !== 'release' && !order) throw new Error('No work order returned');
      const result = command === 'claim' ? await api.claimPager(id) : command === 'release' ? await api.releasePager(id) : await api.pagerAction(id, { action: command, work_order_id: order ?? '' });
      if (!isPagerView(result) || result.technician.technician_id !== id) throw new Error('Invalid pager action response. Refresh the pager before retrying.');
      return result;
    },
    onSuccess: (next) => { qc.setQueryData<PagerView>(pagerKey(id), (old) => newerPager(old, next)); for (const key of ['incident', 'incidents', 'fleet', 'ops', 'learning', 'assets']) void qc.invalidateQueries({ queryKey: [key], predicate: (q) => q.queryKey[1] !== 'pager' }); },
    onError: (e) => { if (e instanceof ApiError && e.status === 409) void pager.refetch(); },
    onSettled: () => { lock.current = false; },
  });
  const fixture = DATA_MODE === 'fixture';
  const data = pager.data; const job = data?.job;
  const queue = data?.technician.queued_work_order_ids.map((id) => ({ id, order: data.queue.find((w) => w.work_order_id === id) })) ?? [];
  const execute = (command: 'claim' | 'release' | 'done') => {
    if (fixture || lock.current || mutation.isPending || !data) return;
    if (command === 'claim' && data.technician.device_controlled !== false) return;
    if (command === 'release' && data.technician.device_controlled !== true) return;
    if (command !== 'claim' && command !== 'release' && !job?.actions.includes(command)) return;
    lock.current = true; mutation.mutate({ command, ...(job ? { order: job.work_order.work_order_id } : {}) });
  };
  return <>
    <PageHeader title="Technician pager" meta="Human review required · device control is not sign-in identity" />
    <div className="mb-5 flex flex-wrap items-center gap-4"><label className="text-sm">Technician ID<input aria-label="Pager technician ID" key={id} defaultValue={id} className={`${inputCls} ml-3 min-h-11`} onKeyDown={(e) => { if (e.key === 'Enter' && e.currentTarget.value.trim()) onTechnicianChange(e.currentTarget.value.trim()); }} onBlur={(e) => { if (e.currentTarget.value.trim() && e.currentTarget.value.trim() !== id) onTechnicianChange(e.currentTarget.value.trim()); }} /></label><StreamStatus stream={pager.stream} /></div>
    {pager.isLoading ? <Loading label="Loading pager…" /> : !data ? <ErrorState error={pager.error} /> : <div className="space-y-6">
      {pager.error && <ErrorState error={pager.error} />}
      <Section title={data.technician.name} aside={<Badge>{data.technician.status}</Badge>}>
        <div className="flex flex-wrap items-center justify-between gap-4"><p>Device-controlled: <strong>{data.technician.device_controlled == null ? 'Not reported' : data.technician.device_controlled ? 'Yes' : 'No'}</strong><span className="ml-3 text-xs text-muted-foreground">DEMO clock {data.demo_time} · version {data.version}</span></p>
          <ConsoleButton className="min-h-12 px-6" variant="primary" aria-busy={mutation.isPending} disabled={fixture || mutation.isPending || data.technician.device_controlled == null} onClick={() => execute(data.technician.device_controlled ? 'release' : 'claim')}>{mutation.isPending && <LoaderCircle aria-hidden className="h-4 w-4 animate-spin motion-reduce:animate-none" />}{data.technician.device_controlled ? 'Release control' : 'Take control'}</ConsoleButton>
        </div>
        {fixture && <p className="mt-3 text-xs text-muted-foreground">{FIXTURE_MUTATION_MESSAGE}</p>}
        {mutation.error && <div role="alert" className="mt-4"><ErrorState error={mutation.error} /><p className="mt-2 text-sm">Review the latest allowed actions before retrying.</p><ConsoleButton className="mt-2 min-h-11" disabled={mutation.isPending} onClick={() => { mutation.reset(); void pager.refetch(); }}>Refresh pager</ConsoleButton></div>}
      </Section>
      <Section title="Current job">
        {job ? <div className="space-y-5">
          <SourceDetails><p>Fictional demo crew; prototype repair workflow. Scenario repair/revenue estimates, not actual billing.</p></SourceDetails><h2 className="text-xl font-semibold leading-relaxed">{job.asset_name ?? job.work_order.title}</h2><Badge tone="accent">{job.work_order.status}</Badge>
          <Fields rows={[["Priority rank", <PriorityRank incidentId={job.incident_id ?? job.work_order.incident_id} />], ["Task", job.work_order.title], ["Work order", job.work_order.work_order_id], ["Location", job.location ?? 'Not reported'], ["Work spot", job.work_order.spot ? `${job.work_order.spot.x}, ${job.work_order.spot.y}` : 'Not reported'], ["Position", data.technician.position ? `${data.technician.position.x}, ${data.technician.position.y}` : 'Coordinates unavailable'], ["Walking remaining", `${job.walking_minutes_left ?? 'Not reported'} DEMO minutes`], ["Progress (fraction)", job.work_order.progress], ["ETA", `${job.work_order.eta_minutes ?? 'Not reported'} DEMO minutes`], ["Risk", job.risk_level ?? 'Not reported'], ["Problem", job.problem ?? 'Not reported'], ["Likely cause", job.likely_cause ?? 'Not reported'], ["Why you", job.why_you], ["Savings if fixed now", `${job.savings_if_fixed_now ?? 'Not reported'} USD`], ["Cost per hour while down", `${job.cost_per_hour_while_down ?? 'Not reported'} USD/h`]]} />
          {!!data.technician.path?.length && <p className="font-mono text-xs">Returned route: {data.technician.path.map((p) => `${p.x},${p.y} (${p.hall_id ?? 'corridor'})`).join(' → ')}</p>}
          <ol className="list-decimal space-y-3 pl-6">{job.steps.map((step, i) => <li key={i}>{step}</li>)}</ol>
          <div className="flex flex-wrap gap-4">{job.asset_id && <AppLink className="inline-flex min-h-11 items-center text-primary underline" to={`/assets/${encodeURIComponent(job.asset_id)}`}>Asset</AppLink>}{job.incident_id && <AppLink className="inline-flex min-h-11 items-center text-primary underline" to={`/incidents/${encodeURIComponent(job.incident_id)}`}>Incident investigation</AppLink>}</div>
          {job.work_order.cost && <div className="overflow-x-auto"><table className="data-table"><caption className="text-left">Returned completed cost · USD</caption><tbody>{Object.entries(job.work_order.cost).map(([key, value]) => <tr key={key}><th>{key}</th><td>{value}</td></tr>)}</tbody></table></div>}
          {job.actions.includes('done') && <ConsoleButton className="min-h-14 min-w-32 px-8 text-base" variant="primary" aria-busy={mutation.isPending} disabled={fixture || mutation.isPending} onClick={() => execute('done')}>{mutation.isPending && <LoaderCircle aria-hidden className="h-4 w-4 animate-spin motion-reduce:animate-none" />}Done</ConsoleButton>}
          {!job.actions.includes('done') && <p className="text-muted-foreground">Completion confirmation not currently available.</p>}
        </div> : <Empty>No current job returned.</Empty>}
      </Section>
      <Section title="Queued jobs">{queue.length ? <div className="overflow-x-auto"><table className="data-table"><thead><tr><th>Work order / task</th><th>Asset</th><th>Priority rank</th><th>Status</th><th>Scheduled / ETA</th></tr></thead><tbody>{queue.map(({ id, order: w }) => <tr key={id}><td>{id}<p>{w?.title ?? 'Work order not reported'}</p></td><td>{w?.asset_name ?? w?.asset_id ?? 'Not reported'}</td><td><PriorityRank incidentId={w?.incident_id} /></td><td>{w?.status ?? 'Not reported'}</td><td>{w?.scheduled_start ?? 'Not reported'} · {w?.eta_minutes ?? 'Not reported'} DEMO minutes</td></tr>)}</tbody></table></div> : <Empty>No queued jobs returned.</Empty>}</Section>
    </div>}
  </>;
}