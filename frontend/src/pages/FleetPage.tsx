import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, FIXTURE_MUTATION_MESSAGE } from '@/api/client';
import { fleetMapQuery, fleetRackQuery, fleetSitesQuery, fleetStatusQuery } from '@/api/fleet-queries';
import type { SiteId } from '@/api/fleet-types';
import { FleetButton, FleetFloor, FleetMachines, FleetMetrics, FleetRackPane } from '@/components/FleetWorkspace';
import { Empty, ErrorMessage, ErrorState, Loading, PageHeader, Section } from '@/components/ui-kit';
import { GpuJobs } from '@/components/GpuJobs';

export function FleetPage({ site, onSiteChange }: { site: SiteId; onSiteChange: (site: SiteId) => void }) {
  return <FleetSiteWorkspace key={site} site={site} onSiteChange={onSiteChange} />;
}
function ClearConfirmation({ children, onCancel }: { children: ReactNode; onCancel: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
    return () => { if (typeof dialog.close === 'function') dialog.close(); };
  }, []);
  return <dialog ref={ref} aria-labelledby="clear-title" aria-describedby="clear-description" onCancel={onCancel} className="fixed inset-0 z-50 m-auto w-[min(92vw,30rem)] rounded-lg border border-rule-strong bg-card p-6 text-foreground backdrop:bg-background">{children}</dialog>;
}
function FleetSiteWorkspace({ site, onSiteChange }: { site: SiteId; onSiteChange: (site: SiteId) => void }) {
  const qc = useQueryClient();
  const sites = useQuery(fleetSitesQuery());
  const map = useQuery(fleetMapQuery(site));
  const status = useQuery(fleetStatusQuery(site));
  const [selected, setSelected] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const rack = useQuery({ ...fleetRackQuery(site, selected ?? ''), enabled: selected !== null });
  const refresh = () => { for (const key of ['fleet', 'assets', 'incidents', 'incident', 'simulation', 'simulations']) void qc.invalidateQueries({ queryKey: [key] }); };
  const mutation = useMutation({ mutationFn: async (action: 'start' | 'stop' | 'fault' | 'clear') => {
    if (api.mode === 'fixture') throw new Error(FIXTURE_MUTATION_MESSAGE);
    if (action === 'start') return api.startFleet({ seed: 42, tick_seconds: 1 });
    if (action === 'stop') return api.stopFleet();
    if (action === 'fault') return api.injectFaults({ count: 3, site });
    return api.clearFleet();
  }, onSettled: refresh, onSuccess: (_data, action) => { if (action === 'clear') { setSelected(null); setConfirm(false); } } });
  const live = status.data?.live ?? map.data?.live ?? sites.data?.live;
  const current = sites.data?.sites.find((s) => s.site_id === site);
  const blocked = api.mode === 'fixture' || mutation.isPending || !live;
  const run = (action: 'start' | 'stop' | 'fault' | 'clear') => { if (!blocked) mutation.mutate(action); };
  return <>
    <PageHeader title="Live fleet" meta={`${current?.name ?? (site === 'mining' ? 'Crypto mining site' : 'Data center')} · simulated readings`} actions={<span className="font-mono text-xs">Loop: {live?.status ?? 'No data'} · {live?.ticks ?? '—'} ticks</span>} />
    <div role="tablist" aria-label="Fleet site" className="mb-4 flex flex-wrap gap-2 border-b border-border pb-3">{(['datacenter', 'mining'] as const).map((id) => <FleetButton key={id} role="tab" aria-selected={site === id} primary={site === id} onClick={() => onSiteChange(id)}>{id === 'datacenter' ? 'Data center' : 'Crypto mining site'}</FleetButton>)}</div>
    <div className="mb-4 flex flex-wrap items-center gap-2">
      <FleetButton primary disabled={blocked || live?.status === 'running'} onClick={() => run('start')}>Start live loop</FleetButton>
      <FleetButton disabled={blocked || live?.status !== 'running'} onClick={() => run('stop')}>Stop live loop</FleetButton>
      <FleetButton disabled={blocked} onClick={() => run('fault')}>Inject 3 faults</FleetButton>
      <FleetButton disabled={blocked} onClick={() => setConfirm(true)}>Clear fleet</FleetButton>
      <span className="text-xs text-muted-foreground">Live loop covers BOTH sites · Faults target {site === 'mining' ? 'Crypto mining site' : 'Data center'}.</span>
    </div>
    {api.mode === 'fixture' && <p className="mb-3 text-xs text-muted-foreground">{FIXTURE_MUTATION_MESSAGE}</p>}
    {mutation.isPending && <p role="status" className="mb-3 text-sm">Backend action pending…</p>}
    {mutation.error && <div role="alert" className="mb-3"><ErrorMessage error={mutation.error} /></div>}
    {mutation.isSuccess && <p role="status" className="mb-3 text-xs">Backend action completed.</p>}
    {confirm && <ClearConfirmation onCancel={() => { if (!mutation.isPending) setConfirm(false); }}>
      <h2 id="clear-title" className="mb-2 font-semibold">Clear fleet across BOTH sites?</h2>
      <p id="clear-description" className="mb-4 text-sm">This deletes all readings, predictions and incidents across BOTH sites, clears faults and resets single-asset simulations. The live loop continues running.</p>
      <div className="flex gap-2"><FleetButton autoFocus disabled={mutation.isPending} onClick={() => setConfirm(false)}>Cancel</FleetButton><FleetButton primary disabled={blocked} onClick={() => run('clear')}>Confirm clear both sites</FleetButton></div>
      {mutation.error && <div role="alert" className="mt-3"><ErrorMessage error={mutation.error} /></div>}
    </ClearConfirmation>}
    <div className="space-y-4">
      <Section title="Site summary">{status.isLoading ? <Loading /> : status.error ? <ErrorState error={status.error} /> : status.data ? <FleetMetrics metrics={status.data.site_metrics} summary={status.data.summary} /> : <Empty>No site status.</Empty>}{sites.error && <ErrorState error={sites.error} />}{sites.isLoading && <Loading label="Loading site directory…" />}{!sites.error && current && <details className="mt-3 text-xs"><summary>Site directory metrics and sources</summary><div className="mt-3"><FleetMetrics metrics={current.site_metrics} /></div></details>}</Section>
      <Section title="Floor map">{map.isLoading ? <Loading /> : map.error ? <ErrorState error={map.error} /> : map.data?.halls.length ? <FleetFloor halls={map.data.halls} gridUnit={map.data.grid_unit} selected={selected} onSelect={setSelected} /> : <Empty>No halls returned.</Empty>}</Section>
      {selected && <Section title={`Rack investigation · ${selected}`} aside={<FleetButton aria-label="Close rack details" onClick={() => setSelected(null)}>×</FleetButton>}>{rack.isLoading ? <Loading /> : rack.error ? <ErrorState error={rack.error} /> : rack.data ? <FleetRackPane rack={rack.data} /> : <Empty>No rack detail.</Empty>}</Section>}
      <Section title="GPU jobs">{map.isLoading ? <Loading /> : map.error ? <ErrorState error={map.error} /> : <GpuJobs jobs={map.data?.jobs} />}</Section>
      <Section title="Machine queue — backend order" flush>{status.isLoading ? <Loading /> : status.error ? <ErrorState error={status.error} /> : <FleetMachines machines={status.data?.machines ?? []} />}</Section>
    </div>
  </>;
}