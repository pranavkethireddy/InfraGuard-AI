import { useQuery } from '@tanstack/react-query';
import { fleetRackQuery } from '@/api/fleet-queries';
import { FleetRackPane } from '@/components/FleetWorkspace';
import { Empty, ErrorState, Loading, PageHeader } from '@/components/ui-kit';
import { IncidentQueue } from '@/components/tables';
import { AppLink } from '@/lib/router-adapter';
export function RackPage({ id }: { id: string }) {
  const q = useQuery(fleetRackQuery('datacenter', id));
  return <><PageHeader title={`Rack ${id}`} meta={<AppLink to="/fleet?site=datacenter" className="text-primary underline">Live fleet map</AppLink>} />{q.isLoading ? <Loading label="Loading rack…" /> : !q.data ? <ErrorState error={q.error} title="Could not load rack" /> : <div className="space-y-6">{q.error && <ErrorState error={q.error} />}<FleetRackPane rack={q.data} /><div><h2 className="mb-3 text-sm font-semibold">Rack incidents</h2>{q.data.incidents.length ? <IncidentQueue incidents={q.data.incidents} /> : <Empty>No incidents returned.</Empty>}</div></div>}</>;
}