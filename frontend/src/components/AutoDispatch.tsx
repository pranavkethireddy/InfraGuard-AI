import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, DATA_MODE } from '@/api/client';
import { ConsoleButton, ErrorState } from './ui-kit';
export function AutoDispatch({ enabled }: { enabled: boolean | undefined }) {
  const qc = useQueryClient();
  const mutation = useMutation({ mutationFn: (next: boolean) => api.setAutoDispatch(next), onSuccess: (data) => {
    qc.setQueriesData({ queryKey: ['ops'], predicate: (q) => q.queryKey[2] === 'technicians' }, (old: unknown) => old && typeof old === 'object' ? { ...old, auto_dispatch: data.enabled } : old);
    void qc.invalidateQueries({ queryKey: ['ops'] });
  }, retry: false });
  return <div className="space-y-3"><ConsoleButton role="switch" aria-label="Automatic dispatch" aria-checked={enabled === true} aria-busy={mutation.isPending} className="min-h-11" disabled={DATA_MODE === 'fixture' || mutation.isPending || enabled === undefined} onClick={() => { if (enabled !== undefined) mutation.mutate(!enabled); }}>Automatic dispatch: {enabled == null ? 'Not reported' : enabled ? 'ON' : 'OFF'}</ConsoleButton>{mutation.error && <ErrorState error={mutation.error} />}</div>;
}