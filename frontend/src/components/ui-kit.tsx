import type { ButtonHTMLAttributes, ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/api/client";
import type { DataOrigin, IncidentStatus, RiskLevel, ScoreKind } from "@/api/types";

export function PageHeader({ title, meta, actions }: { title: string; meta?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-7 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="min-w-0">
        <h1 className="font-display text-[30px] font-semibold leading-tight text-foreground">{title}</h1>
        {meta && <div className="mt-2 max-w-3xl text-[13px] text-muted-foreground">{meta}</div>}
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
    <section className={`min-w-0 rounded-lg border border-border bg-card ${className}`} aria-label={title}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        {aside && <div className="min-w-0 text-xs text-muted-foreground">{aside}</div>}
      </div>
      <div className={flush ? "overflow-x-auto rounded-b-lg" : "min-w-0 overflow-x-auto p-5"}>{children}</div>
    </section>
  );
}

type Tone = "neutral" | "accent" | "attention" | "strong" | "healthy";
const toneCls: Record<Tone, string> = {
  neutral: "border-border bg-muted text-muted-foreground",
  accent: "border-primary/30 bg-accent text-accent-foreground",
  attention: "border-attention/50 bg-attention-surface text-attention-foreground",
  strong: "border-destructive bg-card text-destructive",
  healthy: "border-healthy bg-healthy-surface text-healthy-foreground",
};
export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: Tone }) {
  return (
    <span className={`inline-flex items-center whitespace-nowrap rounded-sm border px-2 py-0.5 text-[11px] font-medium leading-4 ${toneCls[tone]}`}>
      {children}
    </span>
  );
}

const riskTone: Record<RiskLevel, Tone> = { low: "healthy", medium: "attention", high: "strong" };
export function RiskBadge({ level }: { level: RiskLevel | null }) {
  if (!level) return <Badge>Risk: none reported</Badge>;
  return <Badge tone={riskTone[level]}>Risk: {level}</Badge>;
}

const statusTone: Record<IncidentStatus, Tone> = { open: "attention", acknowledged: "accent", resolved: "neutral" };
export function StatusBadge({ status }: { status: IncidentStatus }) {
  return <Badge tone={statusTone[status]}>Status: {status}</Badge>;
}

export function OriginBadge({ origin }: { origin: DataOrigin }) {
  return <SourceDetails><p>data_origin: {origin}</p>{origin === 'simulated' && <p>Synthetic scenario data; not production observations.</p>}</SourceDetails>;
}

export function SourceDetails({ children }: { children: ReactNode }) {
  return <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">Source details</summary><div className="mt-2 space-y-1 break-words">{children}</div></details>;
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
  return new Intl.NumberFormat("en-US", { style: "currency", currency, minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(v);
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

export const btn = "inline-flex min-h-10 items-center justify-center gap-2 rounded-sm px-4 py-2 text-[13px] font-semibold disabled:cursor-not-allowed disabled:opacity-45";
export const btnPrimary = `${btn} bg-primary text-primary-foreground hover:bg-primary/90`;
export const btnOutline = `${btn} border border-input bg-card text-foreground hover:bg-muted`;
export const inputCls = "w-full rounded-sm border border-input bg-background px-3 py-2.5 text-[13px] text-foreground disabled:bg-muted";

/** Router-neutral control shared by both runtime targets. */
export function ConsoleButton({ variant = "outline", className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "outline" | "ghost" }) {
  return <button className={`${variant === "primary" ? btnPrimary : variant === "ghost" ? `${btn} text-foreground hover:bg-muted` : btnOutline} ${className}`} {...props} />;
}
