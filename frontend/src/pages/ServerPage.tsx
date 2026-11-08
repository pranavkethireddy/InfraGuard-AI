import { useQuery } from '@tanstack/react-query';
import { ServerFaultControl } from '@/components/ServerFaultControl';
import { serverQuery } from '@/api/gpu-queries';
import { FleetMachines, PowerDetails, HealthBadge, fieldUnit } from '@/components/FleetWorkspace';
import { GpuJobs } from '@/components/GpuJobs';
import { ReadingsChart } from '@/components/ReadingsChart';
import { AppLink } from '@/lib/router-adapter';
import { Badge, ConsoleButton, Empty, ErrorMessage, ErrorState, Fields, Loading, PageHeader, Section, SourceDetails } from '@/components/ui-kit';
const reported = (v: unknown) => v == null ? 'Not reported' : String(v);
export function ServerPage({ id, gpuIndex, onGpuChange }: { id: string; gpuIndex: number | undefined; onGpuChange: (index: number) => void }) {
  return <ServerWorkspace key={id} id={id} gpuIndex={gpuIndex} onGpuChange={onGpuChange} />;
}
function ServerWorkspace({ id, gpuIndex, onGpuChange }: { id: string; gpuIndex: number | undefined; onGpuChange: (index: number) => void }) {
  const q = useQuery(serverQuery(id));
  if (q.isLoading) return <Loading label="Loading server…" />;
  if (!q.data) return <ErrorState error={q.error} title="Could not load GPU server" />;
  const s = q.data; const m = s.machine;
  const selected = gpuIndex === undefined ? s.gpus[0] : s.gpus.find((g) => g.index === gpuIndex);
  const fields = selected ? [`gpu${selected.index}_temp_c`, `gpu${selected.index}_clock_pct`] : [];
  const histories = fields.filter((f) => m.history.some((r) => r.values[f] != null));
  return <>
    <PageHeader title={m.name} meta={<>{id} · <AppLink to="/fleet?site=datacenter" className="text-primary underline">Rack {s.rack_id} · Live fleet</AppLink></>} actions={<><HealthBadge status={m.status} /><span className="text-xs text-muted-foreground">Heuristic score — not a probability</span><SourceDetails><p>data_origin: simulated</p><p>Synthetic GPU rule scenario; not production observations.</p></SourceDetails></>} />
    {q.error && <ErrorState error={q.error} />}
    <div className="space-y-6">
      <Section title="Server state">
        <PowerDetails item={m} />
        <Fields rows={[["Online", s.online == null ? 'Not reported' : s.online ? 'Online' : 'Offline'], ["Inlet temperature", `${reported(s.inlet_temp_c)} °C`], ["PSU redundancy", `${reported(s.psus_ok)} / ${s.psus_total} PSUs OK`], ["ECC errors", reported(s.ecc_errors)], ["Power", `${reported(s.power_w)} W`], ["Incident", m.active_incident ? <AppLink to={`/incidents/${m.active_incident.incident_id}`} className="text-primary underline">{m.active_incident.incident_id}</AppLink> : 'None returned']]} />
        {m.simulated_fault && <p className="mt-3 text-sm">Simulated fault: {m.simulated_fault.kind} · {m.simulated_fault.phase}</p>}
        <ServerFaultControl servers={[m]} selectedServerId={m.asset_id} error={q.error} />
      </Section>
      <Section title="GPUs" aside={<Badge>{s.gpus.length} returned GPUs</Badge>}>
        <div role="tablist" aria-label="GPU index" className="mb-5 flex flex-wrap gap-2">{s.gpus.map((g) => <ConsoleButton key={g.index} role="tab" aria-selected={selected?.index === g.index} variant={selected?.index === g.index ? 'primary' : 'outline'} onClick={() => onGpuChange(g.index)}>GPU {g.index} · {g.status}</ConsoleButton>)}</div>
        {selected ? <div role="region" aria-label={`GPU ${selected.index} detail`}><Fields rows={[["GPU index", selected.index], ["Temperature", `${reported(selected.temp_c)} °C`], ["Clock", `${reported(selected.clock_pct)} %`], ["State", selected.status], ["Throttle threshold", `${selected.throttle_c} °C`]]} />
          <div className="mt-5 grid gap-5 md:grid-cols-2">{histories.length ? histories.map((f) => <ReadingsChart key={f} readings={m.history.map((r) => ({ ...r, data_origin: 'simulated' }))} field={f} label={f} unit={fieldUnit(f)} height={220} />) : <Empty>GPU history unavailable — no returned GPU readings.</Empty>}</div>
        </div> : <Empty>{gpuIndex === undefined ? 'No GPUs returned.' : `GPU ${gpuIndex} is not returned by this server.`}</Empty>}
        <div className="mt-4 max-w-full overflow-x-auto"><table className="data-table"><thead><tr><th>GPU</th><th>Temperature °C</th><th>Clock %</th><th>State</th><th>Threshold °C</th></tr></thead><tbody>{s.gpus.map((g) => <tr key={g.index}><td>{g.index}</td><td>{reported(g.temp_c)}</td><td>{reported(g.clock_pct)}</td><td>{g.status}</td><td>{g.throttle_c}</td></tr>)}</tbody></table></div>
      </Section>
      <Section title="Server readings"><FleetMachines machines={[m]} />{m.chart_fields.filter((f) => m.history.some((r) => r.values[f] != null)).map((f) => <div className="mt-5" key={f}><ReadingsChart readings={m.history.map((r) => ({ ...r, data_origin: 'simulated' }))} field={f} label={f} unit={fieldUnit(f)} height={220} /></div>)}</Section>
      <Section title="Job"><GpuJobs jobs={s.job ? [s.job] : []} /></Section>
      <Section title="Cooling"><FleetMachines machines={s.cooled_by} /></Section>
    </div>
  </>;
}