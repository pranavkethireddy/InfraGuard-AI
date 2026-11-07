import { useQuery } from "@tanstack/react-query";
import { incidentsQuery } from "@/api/queries";
import { IncidentQueue } from "@/components/tables";
import { Empty, ErrorState, Loading, PageHeader, Section } from "@/components/ui-kit";

export function IncidentsPage() {
  const q = useQuery(incidentsQuery());
  return (
    <>
      <PageHeader title="Incidents" meta={q.data ? `${q.data.total} total · order and priority index as returned by the API` : undefined} />
      <Section title="Incident queue" flush>
        {q.isLoading ? <Loading /> : q.error ? <div className="p-3"><ErrorState error={q.error} /></div>
          : !q.data?.items.length ? <Empty>No incidents.</Empty> : <IncidentQueue incidents={q.data.items} />}
      </Section>
    </>
  );
}
