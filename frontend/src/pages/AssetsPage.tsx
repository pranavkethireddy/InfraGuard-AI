import { useQuery } from "@tanstack/react-query";
import { useState } from 'react';
import { assetsQuery } from "@/api/queries";
import { EquipmentTable } from "@/components/tables";
import { Empty, ErrorState, Loading, PageHeader, Section, btnOutline } from "@/components/ui-kit";

export function AssetsPage() {
  const [offset, setOffset] = useState(0);
  const limit = 50;
  const q = useQuery(assetsQuery(limit, offset));
  return (
    <>
      <PageHeader title="Assets" meta={q.data ? `${q.data.total} total · limit ${q.data.limit} · offset ${q.data.offset}` : undefined} />
      <Section title="Equipment register" flush>
        {q.isLoading ? <Loading /> : q.error ? <div className="p-3"><ErrorState error={q.error} /></div>
          : !q.data?.items.length ? <Empty>No assets registered.</Empty> : <EquipmentTable assets={q.data.items} />}
      </Section>
      <nav aria-label="Assets pagination" className="mt-3 flex items-center justify-between gap-3">
        <button className={btnOutline} disabled={offset === 0 || q.isFetching} onClick={() => setOffset(Math.max(0, offset - limit))}>Previous</button>
        <span className="font-mono text-xs">{q.data ? `${q.data.offset + 1}–${q.data.offset + q.data.items.length} of ${q.data.total}` : 'Loading page'}</span>
        <button className={btnOutline} disabled={!q.data || q.isFetching || q.data.offset + q.data.items.length >= q.data.total} onClick={() => setOffset(offset + limit)}>Next</button>
      </nav>
    </>
  );
}
