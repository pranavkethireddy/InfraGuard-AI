import { useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { LoaderCircle } from 'lucide-react';
import { api } from '@/api/client';
import { fleetChaosQuery } from '@/api/fleet-queries';
import { ConsoleButton, ErrorMessage, Loading } from './ui-kit';

export function ChaosControl() {
  const qc = useQueryClient();
  const lock = useRef(false);
  const options = fleetChaosQuery();
  const mutation = useMutation({
    mutationKey: ['fleet', 'chaos', 'toggle'], retry: false,
    mutationFn: async (enabled: boolean) => {
      await qc.cancelQueries({ queryKey: options.queryKey });
      return api.setFleetChaos({ enabled });
    },
    onSuccess: (next) => {
      qc.setQueryData(options.queryKey, next);
      for (const key of ['fleet', 'incident', 'incidents', 'ops', 'assets', 'whatif']) void qc.invalidateQueries({ queryKey: [key] });
    },
    onSettled: () => { lock.current = false; },
  });
  const state = useQuery({ ...options, enabled: api.mode === 'live' && !mutation.isPending, refetchInterval: mutation.isPending ? false : (options.refetchInterval ?? false) });
  const fixture = api.mode === 'fixture';
  const blocked = fixture || mutation.isPending || state.isFetching || !!state.error || !state.data;
  const toggle = () => {
    if (blocked || lock.current || !state.data) return;
    lock.current = true;
    mutation.mutate(!state.data.enabled);
  };
  return <details className="mb-4 border-y border-border py-3 text-sm">
    <summary className="cursor-pointer text-muted-foreground">Operator controls</summary>
    <div className="mt-3 space-y-3">
      <ConsoleButton role="switch" aria-label="Chaos mode" aria-checked={state.data?.enabled === true} aria-busy={mutation.isPending} disabled={blocked} onClick={toggle}>
        {mutation.isPending && <LoaderCircle aria-hidden className="h-4 w-4 animate-spin motion-reduce:animate-none" />}
        Chaos: {fixture ? 'Unavailable' : state.data ? state.data.enabled ? 'ON' : 'OFF' : 'Not reported'}
      </ConsoleButton>
      {fixture ? <p className="text-xs text-muted-foreground">Unavailable in fixture preview — no approved chaos fixture.</p> : <>
        {state.isLoading && <Loading label="Loading chaos status…" />}
        {state.error && <div role="alert"><ErrorMessage error={state.error} /><ConsoleButton className="mt-2" disabled={state.isFetching || mutation.isPending} onClick={() => void state.refetch()}>Retry chaos status</ConsoleButton></div>}
        {state.data && <dl className="space-y-3 text-xs">
          <div><dt className="text-muted-foreground">Protected technician IDs</dt><dd>{state.data.protected_technicians.length ? <ul className="mt-1 space-y-1 font-mono">{state.data.protected_technicians.map((id) => <li className="break-all" key={id}>{id}</li>)}</ul> : 'None returned'}</dd></div>
          <div><dt className="text-muted-foreground">Active fault IDs</dt><dd>{state.data.active_faults.length ? <ul className="mt-1 space-y-1 font-mono">{state.data.active_faults.map((id) => <li className="break-all" key={id}>{id}</li>)}</ul> : 'None returned'}</dd></div>
        </dl>}
        {mutation.isPending && <p role="status">Chaos change pending…</p>}
        {mutation.error && <div role="alert"><ErrorMessage error={mutation.error} /></div>}
      </>}
    </div>
  </details>;
}