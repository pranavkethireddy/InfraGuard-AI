import { useState, type ReactNode } from "react";
import { AlertTriangle, Boxes, Cpu, LayoutList, Menu, PlayCircle, X } from "lucide-react";
import { API_BASE_URL, DATA_MODE } from "@/api/client";
import { AppLink } from "@/lib/router-adapter";

const nav = [
  { to: "/", label: "Overview", icon: LayoutList, exact: true },
  { to: "/assets", label: "Assets", icon: Boxes, exact: false },
  { to: "/incidents", label: "Incidents", icon: AlertTriangle, exact: false },
  { to: "/simulate", label: "Simulate", icon: PlayCircle, exact: false },
  { to: "/models", label: "Models", icon: Cpu, exact: false },
] as const;

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav aria-label="Main" className="flex flex-col py-2">
      {nav.map((n) => (
        <AppLink key={n.to} to={n.to} onClick={onNavigate} exact={n.exact}
          className="flex items-center gap-2.5 border-l-2 border-transparent px-4 py-1.5 text-[13px] text-sidebar-muted hover:bg-sidebar-accent hover:text-sidebar-foreground"
          activeClassName="!border-primary bg-sidebar-accent !text-sidebar-foreground font-medium">
          <n.icon className="h-3.5 w-3.5" aria-hidden />
          {n.label}
        </AppLink>
      ))}
    </nav>
  );
}

function Brand() {
  return (
    <div className="border-b border-sidebar-border px-4 py-3">
      <p className="font-display text-[15px] font-semibold tracking-tight text-sidebar-foreground">InfraGuard AI</p>
      <p className="text-[11px] text-sidebar-muted">Infrastructure intelligence</p>
    </div>
  );
}

function ModeFooter() {
  return (
    <div className="mt-auto border-t border-sidebar-border px-4 py-3 text-[11px] text-sidebar-muted">
      <p className="eyebrow !text-sidebar-muted">Data source</p>
      <p className="mt-0.5 text-sidebar-foreground">{DATA_MODE === "fixture" ? "Fixture preview" : "Live API"}</p>
      {DATA_MODE === "live" && <p className="break-all font-mono">{API_BASE_URL}</p>}
    </div>
  );
}

export function ModeBanner() {
  if (DATA_MODE === "fixture")
    return (
      <div role="status" className="border-b border-attention/40 bg-attention-surface px-4 py-1.5 text-[13px] text-attention-foreground">
        <strong className="font-semibold">Fixture preview — illustrative data, not live.</strong>{" "}
        <span>Values come from approved contract fixtures. Actions that change data are disabled.</span>
      </div>
    );
  return (
    <div role="status" className="border-b border-border bg-card px-4 py-1.5 text-xs text-muted-foreground">
      Live API · <span className="font-mono">{API_BASE_URL}</span>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex min-h-screen w-full">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:bg-card focus:px-3 focus:py-1.5">Skip to content</a>
      <aside className="sticky top-0 hidden h-screen w-48 shrink-0 flex-col bg-sidebar lg:flex">
        <Brand /><Nav /><ModeFooter />
      </aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <button aria-label="Close menu" className="absolute inset-0 bg-foreground/40" onClick={() => setOpen(false)} />
          <aside className="relative flex h-full w-56 flex-col bg-sidebar">
            <button aria-label="Close menu" onClick={() => setOpen(false)} className="absolute right-2 top-3 p-1 text-sidebar-foreground"><X className="h-4 w-4" /></button>
            <Brand /><Nav onNavigate={() => setOpen(false)} /><ModeFooter />
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 bg-sidebar px-3 py-2 lg:hidden">
          <button aria-label="Open menu" onClick={() => setOpen(true)} className="p-1 text-sidebar-foreground"><Menu className="h-4 w-4" /></button>
          <span className="font-display text-sm font-semibold text-sidebar-foreground">InfraGuard AI</span>
          <span className="text-[11px] text-sidebar-muted">Infrastructure intelligence</span>
        </header>
        <ModeBanner />
        <main id="main" className="w-full max-w-[1400px] flex-1 px-4 py-5 sm:px-6">{children}</main>
      </div>
    </div>
  );
}
