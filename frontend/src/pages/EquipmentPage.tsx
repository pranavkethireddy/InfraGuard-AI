import { useQuery } from '@tanstack/react-query';
import { ApiError } from '@/api/client';
import { fleetStatusQuery } from '@/api/fleet-queries';
import type { SiteId } from '@/api/fleet-types';
import { EquipmentDetails } from '@/components/FacilityEquipment';
import { Empty, ErrorState, Loading, PageHeader, Section } from '@/components/ui-kit';
import { AppLink } from '@/lib/router-adapter';

export function EquipmentPage({ id, site }: { id: string; site: SiteId }) {
  const status = useQuery(fleetStatusQuery(site));
  const machine = status.data?.machines.find((m) => m.asset_id === id);
  if (status.isLoading) return <Loading label="Loading equipment…" />;
  if (status.error) return <ErrorState error={status.error} />;
  return <><PageHeader title={machine?.name ?? `Equipment ${id}`} meta={`${id} · ${site}`} /><AppLink to={`/fleet?site=${site}`} className="mb-4 inline-block text-primary underline">Parent fleet</AppLink>{machine ? <Section title="Equipment"><EquipmentDetails machine={machine} site={site} /></Section> : <><ErrorState error={new ApiError(`Equipment ${id} was not found in returned inventory.`, 404, 'not_found')} /><Empty>No approved equipment data returned.</Empty></>}</>;
}