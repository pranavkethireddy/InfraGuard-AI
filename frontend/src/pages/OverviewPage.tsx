import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fleetMapQuery, fleetRackQuery, fleetStatusQuery } from '@/api/fleet-queries';
import type { SiteId } from '@/api/fleet-types';
import { FleetButton, FleetFloor, FleetMachines, FleetMetrics, FleetRackPane } from '@/components/FleetWorkspace';
import { Badge, Empty, ErrorState, Loading, PageHeader, Section } from '@/components/ui-kit';
import { AppLink } from '@/lib/router-adapter';
import { GpuJobs } from '@/components/GpuJobs';

export function OverviewPage({ site = 'datacenter', onSiteChange = () => {} }: { site?: SiteId; onSiteChange?: (site: SiteId) => void }) {
  return <FacilityOverview key={site} site={site} onSiteChange={onSiteChange} />;
}
function FacilityOverview({ site, onSiteChange }: { site: SiteId; onSiteChange: (site: SiteId) => void }) {
  const map = useQuery(fleetMapQuery(site));
  const status = useQuery(fleetStatusQuery(site));
  const [selected, setSelected] = useState<string | null>(null);
  const rack = useQuery({ ...fleetRackQuery(site, selected ?? ''), enabled: selected !== null });
  const machines = status.data?.machines ?? [];
  const affected = machines.filter((m) => m.status !== 'healthy' || m.power_state === 'off' || m.power_state === 'at_risk' || m.active_incident);
  const incidents = machines.filter((m) => m.active_incident);
  const live = status.data?.live ?? map.data?.live;
  return <>
    <PageHeader title="Overview" meta={`${site === 'mining' ? 'Crypto mining site' : 'Data center'} · simulated facility readings`}
      actions={<><Badge>Live loop: {live?.status ?? 'Not reported'}</Badge><AppLink to={`/fleet?site=${site}`} className="rounded-sm border border-input px-4 py-2 text-sm font-semibold text-primary">Start loop / inject faults →</AppLink></>} />
    <div role="tablist" aria-label="Overview site" className="mb-5 flex flex-wrap gap-2">{(['datacenter', 'mining'] as const).map((id) => <FleetButton key={id} role="tab" aria-selected={site === id} primary={site === id} onClick={() => onSiteChange(id)}>{id === 'datacenter' ? 'Data center' : 'Crypto mining site'}</FleetButton>)}</div>
    <div className="space-y-6">
      <Section title="Facility floor map">
        {map.isLoading ? <Loading label="Loading facility map…" /> : map.error ? <ErrorState error={map.error} /> : map.data?.halls.length ? <FleetFloor halls={map.data.halls} gridUnit={map.data.grid_unit} selected={selected} onSelect={setSelected} /> : <Empty>No facility map returned.</Empty>}
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