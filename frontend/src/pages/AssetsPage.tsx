import { useQuery } from "@tanstack/react-query";
import { assetsQuery } from "@/api/queries";
import { EquipmentTable } from "@/components/tables";
import { Empty, ErrorState, Loading, PageHeader, Section } from "@/components/ui-kit";

export function AssetsPage() {
  const q = useQuery(assetsQuery());
  return (
    <>
      <PageHeader title="Assets" meta={q.data ? `${q.data.total} total · limit ${q.data.limit} · offset ${q.data.offset}` : undefined} />
      <Section title="Equipment register" flush>
        {q.isLoading ? <Loading /> : q.error ? <div className="p-3"><ErrorState error={q.error} /></div>
          : !q.data?.items.length ? <Empty>No assets registered.</Empty> : <EquipmentTable assets={q.data.items} />}
      </Section>
    </>
  );
}
