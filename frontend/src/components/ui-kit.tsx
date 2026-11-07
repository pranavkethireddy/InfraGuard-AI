import type { ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/api/client";
import type { DataOrigin, IncidentStatus, RiskLevel, ScoreKind } from "@/api/types";

export function PageHeader({ title, meta, actions }: { title: string; meta?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-x-6 gap-y-2 border-b border-rule-strong pb-3">
      <div className="min-w-0">
        <h1 className="font-display text-[22px] font-semibold leading-tight tracking-tight text-foreground">{title}</h1>
        {meta && <div className="mt-1 font-mono text-xs text-muted-foreground">{meta}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-1.5">{actions}</div>}
    </header>
  );
}

/** A bordered workspace block with a thin header rule. */
export function Section({ title, aside, children, flush = false, className = "" }: {
  title: string; aside?: ReactNode; children: ReactNode; flush?: boolean; className?: string;
}) {
  return (
    <section className={`border border-border bg-card ${className}`} aria-label={title}>
      <div className="flex items-center justify-between gap-3 border-b border-border px-3 py-2">
        <h2 className="eyebrow !text-foreground">{title}</h2>
        {aside && <div className="shrink-0 whitespace-nowrap text-xs text-muted-foreground">{aside}</div>}
      </div>
      <div className={flush ? "" : "p-3"}>{children}</div>
    </section>
  );
}

type Tone = "neutral" | "accent" | "attention" | "strong";
const toneCls: Record<Tone, string> = {
  neutral: "border-border bg-muted text-muted-foreground",
  accent: "border-primary/30 bg-accent text-accent-foreground",
  attention: "border-attention/50 bg-attention-surface text-attention-foreground",
  strong: "border-attention bg-attention text-foreground",
};
export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: Tone }) {
  return (
    <span className={`inline-flex items-center whitespace-nowrap rounded-sm border px-1.5 py-px text-[11px] font-medium leading-4 ${toneCls[tone]}`}>
      {children}
    </span>
  );
}

const riskTone: Record<RiskLevel, Tone> = { low: "neutral", medium: "attention", high: "strong" };
export function RiskBadge({ level }: { level: RiskLevel | null }) {
  if (!level) return <Badge>Risk: none reported</Badge>;
  return <Badge tone={riskTone[level]}>Risk: {level}</Badge>;
}

const statusTone: Record<IncidentStatus, Tone> = { open: "attention", acknowledged: "accent", resolved: "neutral" };
export function StatusBadge({ status }: { status: IncidentStatus }) {
  return <Badge tone={statusTone[status]}>Status: {status}</Badge>;
}

export function OriginBadge({ origin }: { origin: DataOrigin }) {
  return origin === "simulated" ? <Badge>Simulated data</Badge> : <Badge tone="accent">Observed data</Badge>;
}

export const SCORE_KIND_LABEL: Record<ScoreKind, string> = {
  heuristic: "Heuristic score — not a probability",
  model_score: "Uncalibrated model score — not a probability",
  calibrated_probability: "Calibrated probability",
};

/** Displays a server-provided score exactly as returned, labelled by its kind. */
export function ScoreValue({ score, kind }: { score: number; kind: ScoreKind }) {
  return (
    <span className="inline-flex flex-wrap items-baseline gap-2">
      <span className="font-mono text-base font-semibold text-foreground">{String(score)}</span>
      <span className="text-xs text-muted-foreground">{SCORE_KIND_LABEL[kind]}</span>
    </span>
  );
}

/** Two-column label/value list. */
export function Fields({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[minmax(7rem,auto)_1fr] gap-x-4 gap-y-1.5 text-[13px]">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted-foreground">{k}</dt>
          <dd className="min-w-0 break-words">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export const Mono = ({ children }: { children: ReactNode }) => <span className="font-mono text-[12.5px]">{children}</span>;

export function money(v: number | null | undefined, currency = "USD") {
  if (v == null) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(v);
}
/** Deterministic UTC timestamp: 2026-11-07 20:00 UTC */
export function dt(v: string | null | undefined) {
  if (!v) return "—";
  return `${v.slice(0, 16).replace("T", " ")} UTC`;
}
export const val = (v: unknown) => (v === null || v === undefined ? "—" : String(v));

export function ErrorMessage({ error }: { error: unknown }) {
  const e = error instanceof ApiError ? error : null;
  return (
    <div className="text-[13px]">
      <p className="text-foreground">{error instanceof Error ? error.message : String(error)}</p>
      {e && (
        <p className="mt-0.5 font-mono text-xs text-muted-foreground">
          {e.status ? `HTTP ${e.status} · ` : ""}{e.code}{e.requestId ? ` · request_id ${e.requestId}` : ""}
        </p>
      )}
    </div>
  );
}

export function ErrorState({ error, title = "Could not load data" }: { error: unknown; title?: string }) {
  const qc = useQueryClient();
  return (
    <div role="alert" className="border border-destructive/40 border-l-2 border-l-destructive bg-card p-3">
      <p className="mb-1 text-[13px] font-semibold text-destructive">{title}</p>
      <ErrorMessage error={error} />
      <button onClick={() => qc.refetchQueries({ type: "active" })} className={`${btnOutline} mt-2`}>Retry</button>
    </div>
  );
}

export const Empty = ({ children }: { children: ReactNode }) => (
  <p className="px-3 py-4 text-[13px] text-muted-foreground">{children}</p>
);
export const Loading = ({ label = "Loading…" }: { label?: string }) => (
  <p className="px-3 py-4 text-[13px] text-muted-foreground" role="status">{label}</p>
);

export const btn = "inline-flex items-center justify-center rounded-sm px-3 py-1.5 text-[13px] font-medium disabled:cursor-not-allowed disabled:opacity-45";
export const btnPrimary = `${btn} bg-primary text-primary-foreground hover:bg-primary/90`;
export const btnOutline = `${btn} border border-input bg-card text-foreground hover:bg-muted`;
export const inputCls = "w-full rounded-sm border border-input bg-card px-2.5 py-1.5 text-[13px] text-foreground disabled:bg-muted";
