import type { DetectorModel, EvaluationMetrics } from "@/api/types";
import { Badge, Fields, Mono, SCORE_KIND_LABEL, Section, val } from "./ui-kit";

export function evaluationLabel(m: DetectorModel): string {
  if (m.evaluation_status === "evaluated" && m.metrics) return "Evaluated";
  if (m.evaluation_status === "not_applicable") return "Not applicable (rule)";
  return "Not evaluated";
}

/** Renders backend-reported evaluation metrics verbatim. Never shown unless returned by the API. */
export function MetricsTable({ metrics: m }: { metrics: EvaluationMetrics }) {
  const scores: [string, unknown][] = [["precision", m.precision], ["recall", m.recall], ["f1", m.f1], ["pr_auc", m.pr_auc], ["roc_auc", m.roc_auc], ["brier", m.brier]];
  return (
    <div className="space-y-3" aria-label="Evaluation metrics">
      <Fields rows={[
        ["Split", <Mono>{m.split}</Mono>],
        ["Evaluated", <Mono>{m.evaluated_at}</Mono>],
        ["Dataset", m.dataset_version],
        ["Samples", <Mono>n={m.n} · positives={m.positives}</Mono>],
        ["Threshold", <Mono>{val(m.threshold)}{m.threshold_selection ? ` (${m.threshold_selection})` : ""}</Mono>],
        ["Calibrated", m.calibrated ? "Yes" : "No — scores are not probabilities"],
        ["Seed", <Mono>{val(m.seed)}</Mono>],
      ]} />
      <table className="data-table">
        <caption className="sr-only">Scores</caption>
        <thead><tr><th>Metric</th><th className="text-right">Model</th><th className="text-right">Baseline{m.baseline ? ` (${m.baseline.name})` : ""}</th></tr></thead>
        <tbody className="font-mono">
          {scores.map(([k, v]) => (
            <tr key={k}><td>{k}</td><td className="text-right">{val(v)}</td>
              <td className="text-right">{m.baseline && (k === "f1" || k === "pr_auc") ? val(m.baseline[k]) : "—"}</td></tr>
          ))}
        </tbody>
      </table>
      {m.confusion_matrix && (
        <table className="data-table w-auto">
          <caption className="eyebrow mb-1 text-left">Confusion matrix</caption>
          <thead><tr><th></th><th className="text-right">Predicted +</th><th className="text-right">Predicted −</th></tr></thead>
          <tbody className="font-mono">
            <tr><th scope="row">Actual +</th><td className="text-right">tp {m.confusion_matrix.tp}</td><td className="text-right">fn {m.confusion_matrix.fn}</td></tr>
            <tr><th scope="row">Actual −</th><td className="text-right">fp {m.confusion_matrix.fp}</td><td className="text-right">tn {m.confusion_matrix.tn}</td></tr>
          </tbody>
        </table>
      )}
      {m.metrics_file && <p className="text-xs text-muted-foreground">Source: <Mono>{m.metrics_file}</Mono></p>}
    </div>
  );
}

export function ModelCard({ model: m }: { model: DetectorModel }) {
  const synthetic = /synthetic|ai4i/i.test([m.source_dataset, ...m.limitations].join(" "));
  return (
    <Section title={m.model_name} aside={<Mono>{m.detector_id} · v{m.model_version}</Mono>}>
      <div className="mb-3 flex flex-wrap gap-1.5">
        {m.status === "available" ? <Badge tone="accent">Available</Badge> : <Badge tone="attention">Unavailable</Badge>}
        <Badge>{m.kind === "rule" ? "Rule" : "ML"}</Badge>
        <Badge>{evaluationLabel(m)}</Badge>
        {synthetic && <Badge tone="attention">Synthetic benchmark data</Badge>}
      </div>
      <Fields rows={[
        ["Score type", SCORE_KIND_LABEL[m.score_kind]],
        ["Target", m.target],
        ["Asset types", <Mono>{m.asset_types.join(", ")}</Mono>],
        ["Horizon", m.prediction_horizon_hours == null ? "None (not a forecast)" : <Mono>{m.prediction_horizon_hours} h</Mono>],
        ["Evaluation", evaluationLabel(m)],
        ["Source dataset", m.source_dataset ?? "—"],
        ["Risk thresholds", m.risk_thresholds ? <Mono>{Object.entries(m.risk_thresholds).map(([k, v]) => `${k} ≥ ${v}`).join(" · ")}</Mono> : "—"],
        ["Model card", m.model_card_url ? <Mono>{m.model_card_url}</Mono> : "—"],
      ]} />
      {m.rule_config && (
        <table className="data-table mt-3">
          <caption className="eyebrow mb-1 text-left">Rule configuration</caption>
          <tbody className="font-mono">{Object.entries(m.rule_config).map(([k, v]) => <tr key={k}><td>{k}</td><td className="text-right">{val(v)}</td></tr>)}</tbody>
        </table>
      )}
      <table className="data-table mt-3">
        <caption className="eyebrow mb-1 text-left">Input fields</caption>
        <thead><tr><th>Field</th><th>Unit</th><th>Required</th></tr></thead>
        <tbody>{m.input_fields.map((f) => <tr key={f.name}><td className="font-mono">{f.name}</td><td className="font-mono">{f.unit ?? "—"}</td><td>{f.required ? "Required" : "Optional"}</td></tr>)}</tbody>
      </table>
      {m.evaluation_status === "evaluated" && m.metrics ? (
        <div className="mt-3"><MetricsTable metrics={m.metrics} /></div>
      ) : (
        <p className="mt-3 text-[13px] text-muted-foreground">No evaluation metrics returned by the API.</p>
      )}
      {m.limitations.length > 0 && (
        <div className="mt-3 border-t border-border pt-2">
          <p className="eyebrow">Limitations</p>
          <ul className="mt-1 list-disc pl-5 text-[13px]">{m.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
        </div>
      )}
    </Section>
  );
}
