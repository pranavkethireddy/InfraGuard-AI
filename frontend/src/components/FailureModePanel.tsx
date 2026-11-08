import type { FailureMode } from '@/api/types';
import { Fields, SourceDetails } from './ui-kit';
export function FailureModePanel({ mode }: { mode?: FailureMode | null | undefined }) {
  if (!mode) return <p className="text-sm text-muted-foreground">Failure mode: Not reported</p>;
  return <div className="space-y-4" role="region" aria-label="Failure mode">
    <h3 className="font-semibold">{mode.title}</h3>
    <div><h4 className="eyebrow mb-1">Cause</h4><p className="break-words text-sm">{mode.cause || 'Not reported'}</p></div>
    <div><h4 className="eyebrow mb-1">Why we think so</h4><p className="break-words text-sm">{mode.reasoning || 'Not reported'}</p></div>
    <div><h4 className="eyebrow mb-1">Signals &amp; evidence</h4>
      {mode.signals.length ? <ul className="list-disc pl-5 text-sm">{mode.signals.map((s) => <li key={s} className="break-words font-mono">{s}</li>)}</ul> : <p>Signals: Not reported</p>}
      <Fields rows={Object.entries(mode.evidence).map(([k, v]) => [k, String(v)])} />
    </div>
    <div><h4 className="eyebrow mb-1">Steps</h4>{mode.steps.length ? <ol className="list-decimal space-y-1 pl-5 text-sm">{mode.steps.map((step, i) => <li key={i}>{step}</li>)}</ol> : <p>Not reported</p>}</div>
    <Fields rows={[["Repair time", mode.repair_hours == null ? 'Not reported' : `${mode.repair_hours} h`], ["Parts cost", mode.parts_cost_usd == null ? 'Not reported' : `${mode.parts_cost_usd} USD`]]} />
    <p className="text-xs text-attention-foreground">A human must approve physical work.</p>
    <SourceDetails><p>mode_id: {mode.mode_id}</p><p>Backend-reported diagnosis and repair assumptions; not a verified diagnosis, measured cost or vendor quote.</p></SourceDetails>
  </div>;
}