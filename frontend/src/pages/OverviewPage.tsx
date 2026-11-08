import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fleetMapQuery, fleetRackQuery, fleetStatusQuery } from '@/api/fleet-queries';
import type { SiteId } from '@/api/fleet-types';
import { FleetButton, FleetFloor, FleetMachines, FleetMetrics, FleetRackPane } from '@/components/FleetWorkspace';
import { Badge, Empty, ErrorState, Loading, PageHeader, Section, SourceDetails } from '@/components/ui-kit';
import { AppLink } from '@/lib/router-adapter';
import { GpuJobs } from '@/components/GpuJobs';
import { api } from '@/api/client';
import { useCrewStream } from '@/api/ops-stream';
import { SiteFloor } from '@/components/SiteFloor';
import { StreamStatus } from '@/components/StreamStatus';

export function OverviewPage({ site = 'datacenter', onSiteChange = () => {} }: { site?: SiteId; onSiteChange?: (site: SiteId) => void }) {
  return <FacilityOverview key={site} site={site} onSiteChange={onSiteChange} />;
}
function FacilityOverview({ site, onSiteChange }: { site: SiteId; onSiteChange: (site: SiteId) => void }) {
  const map = useQuery(fleetMapQuery(site));
  const status = useQuery(fleetStatusQuery(site));
  const floor = useQuery({ queryKey: ['ops', site, 'floor'], queryFn: async () => {
    const value = await api.opsFloor(site);
    if (!Array.isArray(value.halls) || value.site_id !== site || !Number.isFinite(value.width) || !Number.isFinite(value.depth)) throw new Error('Invalid floor response');
    return value;
  } });
  const crew = useCrewStream(site);
  const [selected, setSelected] = useState<string | null>(null);
  const rack = useQuery({ ...fleetRackQuery(site, selected ?? ''), enabled: selected !== null });
  const machines = status.data?.machines ?? [];
  const affected = machines.filter((m) => m.status !== 'healthy' || m.power_state === 'off' || m.power_state === 'at_risk' || m.active_incident);
  const incidents = machines.filter((m) => m.active_incident);
  const live = status.data?.live ?? map.data?.live;
  return <>
    <PageHeader title="Overview" meta={`${site === 'mining' ? 'Crypto mining site' : 'Data center'}`}
      actions={<><Badge>Live loop: {live?.status ?? 'Not reported'}</Badge><AppLink to={`/fleet?site=${site}`} className="rounded-sm border border-input px-4 py-2 text-sm font-semibold text-primary">Start loop / inject faults →</AppLink></>} />
    <div role="tablist" aria-label="Overview site" className="mb-5 flex flex-wrap gap-2">{(['datacenter', 'mining'] as const).map((id) => <FleetButton key={id} role="tab" aria-selected={site === id} primary={site === id} onClick={() => onSiteChange(id)}>{id === 'datacenter' ? 'Data center' : 'Crypto mining site'}</FleetButton>)}</div>
    <SourceDetails><p>data_origin: simulated · synthetic facility scenario; not production observations.</p><p>Fictional crew; walking and repair durations use DEMO time.</p>{crew.data?.assumptions_source && <p>assumptions_source: {crew.data.assumptions_source}</p>}</SourceDetails><div className="mt-4 space-y-6">
      <Section title="Facility floor map">
        <div className="mb-4 flex flex-wrap items-center gap-4"><Badge>Auto dispatch: {crew.data?.auto_dispatch == null ? 'Not reported' : crew.data.auto_dispatch ? 'ON' : 'OFF'}</Badge><StreamStatus stream={crew.stream} /></div>
        {crew.error && <ErrorState error={crew.error} />}
        {map.isLoading || floor.isLoading ? <Loading label="Loading facility map…" /> : map.error ? <ErrorState error={map.error} /> : floor.data && map.data ? <SiteFloor key={site} floor={floor.data} halls={map.data.halls} technicians={crew.data?.technicians ?? []} selected={selected} onSelect={setSelected} /> : <>{floor.error && <ErrorState error={floor.error} />}{map.data?.halls.length ? <FleetFloor halls={map.data.halls} gridUnit={map.data.grid_unit} selected={selected} onSelect={setSelected} /> : <Empty>No facility map returned.</Empty>}</>}
      </Section>
      <Section title="Facility status">
        {status.isLoading ? <Loading label="Loading facility status…" /> : status.error ? <ErrorState error={status.error} /> : status.data ? <>
          {status.data.summary.no_data > 0 || status.data.summary.machines === 0 ? <p role="status" className="mb-4 text-sm text-muted-foreground">No data for some or all machines. Facility health is not fully known.</p> : null}
          <FleetMetrics metrics={status.data.site_metrics} summary={status.data.summary} />
        </> : <Empty>No facility status reported.</Empty>}
      </Section>
      {selected && <Section title={`Rack investigation · ${selected}`} aside={<FleetButton aria-label="Close rack details" onClick={() => setSelected(null)}>×</FleetButton>}>{rack.isLoading ? <Loading /> : rack.error ? <ErrorState error={rack.error} /> : rack.data ? <FleetRackPane rack={rack.data} /> : <Empty>No rack details returned.</Empty>}</Section>}
      <Section title="GPU jobs">{map.isLoading ? <Loading /> : map.error ? <ErrorState error={map.error} /> : <GpuJobs jobs={map.data?.jobs} />}</Section>
      <Section title="Affected machines — backend order" flush>{status.isLoading ? <Loading /> : status.error ? <ErrorState error={status.error} /> : affected.length ? <FleetMachines machines={affected} /> : <Empty>No affected machines reported. Power availability may be unreported.</Empty>}</Section>
      <Section title="Incident queue" aside={<AppLink to="/incidents" className="text-primary underline">All incidents</AppLink>} flush>{status.isLoading ? <Loading /> : status.error ? <ErrorState error={status.error} /> : incidents.length ? <FleetMachines machines={incidents} /> : <Empty>No active incidents reported.</Empty>}</Section>
    </div>
  </>;
}