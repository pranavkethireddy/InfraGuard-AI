import { useQuery } from '@tanstack/react-query';
import { incidentQuery } from '@/api/queries';
import type { IncidentSummary } from '@/api/types';
import { ErrorMessage } from './ui-kit';

/** Never derive rank from index, risk, response order or work-order fields. */
export function RankValue({ rank }: { rank: IncidentSummary['priority_rank'] }) {
  return <span className="font-mono">{rank == null ? 'Not reported' : rank}</span>;
}
export function PriorityRank({ incidentId }: { incidentId: string | null | undefined }) {
  const q = useQuery({ ...incidentQuery(incidentId ?? ''), enabled: !!incidentId, retry: false });
  if (!incidentId) return <RankValue rank={null} />;
  if (q.isLoading) return <span role="status">Loading rank…</span>;
  if (q.error) return <span role="alert">Rank unavailable · <ErrorMessage error={q.error} /></span>;
  return <RankValue rank={q.data?.priority_rank} />;
}