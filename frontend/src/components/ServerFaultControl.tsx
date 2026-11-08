import { useRef, useState } from 'react';
import { useIsMutating, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, FIXTURE_MUTATION_MESSAGE } from '@/api/client';
import type { MachineStatus } from '@/api/fleet-types';
import { ConsoleButton, ErrorMessage, inputCls } from './ui-kit';

export function ServerFaultControl({ servers, loading = false, error, disabled = false, selectedServerId }: {
  servers: MachineStatus[]; loading?: boolean; error?: unknown; disabled?: boolean; selectedServerId?: string;
}) {
  const [selection, setSelection] = useState(selectedServerId ?? '');
  const [kind, setKind] = useState<'gpu_fault' | 'server_crash'>('gpu_fault');
  const inventory = servers.filter((s) => s.asset_type === 'gpu_server');
  const selected = inventory.find((s) => s.asset_id === selection);
  const lock = useRef(false);
  const qc = useQueryClient();
  const pending = useIsMutating({ mutationKey: ['fleet', 'action'] }) > 0;
  const fault = useMutation({ mutationKey: ['fleet', 'action', 'server-fault'], retry: false,
    mutationFn: ({ id, faultKind }: { id: string; faultKind: 'gpu_fault' | 'server_crash' }) => api.injectFaults({ asset_ids: [id], kind: faultKind }),
    onSettled: () => { lock.current = false; for (const key of ['fleet', 'assets', 'incidents', 'incident', 'ops']) void qc.invalidateQueries({ queryKey: [key] }); },
  });
  const blocked = api.mode === 'fixture' || loading || !!error || disabled || pending || !selected;
  return <div role="region" aria-label="GPU server fault controls" className="mb-4 space-y-3 border-t border-border pt-4">
    <div className="flex flex-wrap items-end gap-3">
      <label className="min-w-0 text-xs">GPU server<select aria-label="GPU server" className={`${inputCls} mt-1 max-w-full`} value={selected?.asset_id ?? ''} disabled={api.mode === 'fixture' || loading || !!error || disabled || pending || !inventory.length || !!selectedServerId} onChange={(e) => { setSelection(e.target.value); fault.reset(); }}>
        <option value="">{loading ? 'Loading GPU servers…' : 'Select GPU server'}</option>{inventory.map((s) => <option key={s.asset_id} value={s.asset_id}>{s.name} ({s.asset_id})</option>)}
      </select></label>
      <label className="text-xs">Fault choice<select aria-label="Server fault choice" className={`${inputCls} mt-1`} value={kind} disabled={blocked} onChange={(e) => { setKind(e.target.value === 'server_crash' ? 'server_crash' : 'gpu_fault'); fault.reset(); }}><option value="gpu_fault">GPU fails</option><option value="server_crash">Whole server down</option></select></label>
      <ConsoleButton disabled={blocked} aria-busy={fault.isPending} onClick={() => { if (blocked || lock.current || !selected) return; lock.current = true; fault.mutate({ id: selected.asset_id, faultKind: kind }); }}>{fault.isPending ? 'Injecting…' : 'Inject server fault'}</ConsoleButton>
    </div>
    {loading ? <p role="status">Loading GPU server inventory…</p> : error ? <div role="alert"><ErrorMessage error={error} /></div> : !inventory.length ? <p>No GPU servers returned.</p> : null}
    {api.mode === 'fixture' && <p className="text-xs text-muted-foreground">{FIXTURE_MUTATION_MESSAGE}</p>}
    {fault.error && <div role="alert"><ErrorMessage error={fault.error} /></div>}{fault.isSuccess && <p role="status">Server fault request completed.</p>}
  </div>;
}