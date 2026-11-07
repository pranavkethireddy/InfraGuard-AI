import { useQuery } from "@tanstack/react-query";
import { modelsQuery } from "@/api/queries";
import { ModelCard } from "@/components/ModelCard";
import { Empty, ErrorState, Loading, PageHeader } from "@/components/ui-kit";

export function ModelsPage() {
  const q = useQuery(modelsQuery());
  return (
    <>
      <PageHeader title="Models" meta="Registered detectors. Metrics appear only when the API returns them." />
      {q.isLoading ? <Loading /> : q.error ? <ErrorState error={q.error} /> : !q.data?.items.length ? <Empty>No detectors registered.</Empty> : (
        <div className="grid gap-4 xl:grid-cols-2">{q.data.items.map((m) => <ModelCard key={m.detector_id} model={m} />)}</div>
      )}
    </>
  );
}
