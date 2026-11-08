import { useRef, useState } from 'react';
import { useIsMutating, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, FIXTURE_MUTATION_MESSAGE } from '@/api/client';
import { facilityFaults } from '@/api/facility-spec';
import type { FaultKind, MachineStatus } from '@/api/fleet-types';
import { ConsoleButton, ErrorMessage, inputCls } from './ui-kit';

export function EquipmentFaultControl({ machines, loading = false, error }: { machines: MachineStatus[]; loading?: boolean; error?: unknown }) {
  const [id, setId] = useState('');
  const [kind, setKind] = useState<FaultKind | undefined>();
  const inventory = machines.filter((m) => facilityFaults[m.asset_type]);
  const selected = inventory.find((m) => m.asset_id === id);
  const choices = selected ? facilityFaults[selected.asset_type] ?? [] : [];
  const currentKind = kind && choices.includes(kind) ? kind : choices[0];
  const lock = useRef(false);
  const qc = useQueryClient();
  const pending = useIsMutating({ mutationKey: ['fleet', 'action'] }) > 0;
  const fault = useMutation({ mutationKey: ['fleet', 'action', 'equipment-fault'], retry: false,
    mutationFn: (body: { asset_ids: string[]; kind: FaultKind }) => api.injectFaults(body),
    onSettled: () => { lock.current = false; },
    onSuccess: () => { for (const key of ['fleet', 'assets', 'incidents', 'incident', 'ops']) void qc.invalidateQueries({ queryKey: [key] }); },
  });
  const blocked = api.mode === 'fixture' || loading || !!error || pending;
  return <details className="mb-4 border-t border-border pt-3"><summary className="cursor-pointer text-sm">Facility fault controls</summary>
    <div role="region" aria-label="Facility fault controls" className="mt-3 space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <label className="min-w-0 text-xs">Equipment<select aria-label="Facility equipment" className={`${inputCls} mt-1 max-w-full`} value={selected?.asset_id ?? ''} disabled={blocked} onChange={(e) => { setId(e.target.value); setKind(undefined); fault.reset(); }}><option value="">{loading ? 'Loading equipment…' : 'Select equipment'}</option>{inventory.map((m) => <option key={m.asset_id} value={m.asset_id}>{m.name} ({m.asset_id}) · {m.asset_type}</option>)}</select></label>
        <label className="text-xs">Fault choice<select aria-label="Facility fault choice" className={`${inputCls} mt-1`} value={currentKind ?? ''} disabled={blocked || !selected} onChange={(e) => { const next = choices.find((v) => v === e.target.value); setKind(next); fault.reset(); }}>{!choices.length && <option value="">Not available</option>}{choices.map((v) => <option key={v} value={v}>{v.replaceAll('_', ' ')}</option>)}</select></label>
        <ConsoleButton disabled={blocked || !selected || !currentKind} aria-busy={fault.isPending} onClick={() => { if (blocked || lock.current || !selected || !currentKind) return; lock.current = true; fault.mutate({ asset_ids: [selected.asset_id], kind: currentKind }); }}>{fault.isPending ? 'Injecting…' : 'Inject equipment fault'}</ConsoleButton>
      </div>
      {loading ? <p role="status">Loading equipment inventory…</p> : error ? <div role="alert"><ErrorMessage error={error} /></div> : !inventory.length ? <p>No compatible facility equipment returned.</p> : null}
      {api.mode === 'fixture' && <p className="text-xs text-muted-foreground">{FIXTURE_MUTATION_MESSAGE}</p>}
      {fault.error && <div role="alert"><ErrorMessage error={fault.error} /></div>}{fault.isSuccess && <p role="status">Equipment fault request completed.</p>}
    </div>
  </details>;
}