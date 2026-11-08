import { useState, type ReactNode } from "react";
import { AlertTriangle, Boxes, ChevronRight, LayoutList, Menu, ShieldCheck, X } from "lucide-react";
import { API_BASE_URL, DATA_MODE } from "@/api/client";
import { AppLink } from "@/lib/router-adapter";
import { ConsoleButton } from "./ui-kit";

const nav = [
  { to: "/", label: "Overview", icon: LayoutList, exact: true },
  { to: "/fleet", label: "Live fleet", icon: Boxes, exact: false },
  { to: "/operations", label: "Operations", icon: LayoutList, exact: false },
  { to: "/pager", label: "Technician pager", icon: ShieldCheck, exact: false },
  { to: "/assets", label: "Assets", icon: Boxes, exact: false },
  { to: "/incidents", label: "Incidents", icon: AlertTriangle, exact: false },
] as const;

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav aria-label="Main" className="flex flex-col gap-1 px-3 py-5">
      {nav.map((n) => (
        <AppLink key={n.to} to={n.to} onClick={onNavigate} exact={n.exact}
          className="flex min-h-11 items-center gap-3 rounded-sm px-3 py-2 text-[13px] text-sidebar-muted hover:bg-muted hover:text-sidebar-foreground"
          activeClassName="!bg-primary !text-primary-foreground font-semibold">
          <n.icon className="h-4 w-4" aria-hidden />
          {n.label}
        </AppLink>
      ))}
    </nav>
  );
}

function Brand() {
  return (
    <div className="border-b border-border px-5 py-6">
      <div className="flex items-center gap-2 text-sidebar-foreground"><ShieldCheck className="h-5 w-5 text-primary" aria-hidden /><p className="font-display text-[18px] font-bold">InfraGuard AI</p></div>
      <p className="mt-1 text-[11px] text-sidebar-muted">Infrastructure intelligence</p>
    </div>
  );
}

function ModeFooter() {
  return (
    <div className="mx-3 mb-3 mt-auto rounded-md border border-border bg-background p-4 text-[11px] text-sidebar-muted">
      <p className="eyebrow !text-sidebar-muted">Data source</p>
      <p className="mt-0.5 text-sidebar-foreground">{DATA_MODE === "fixture" ? "Fixture preview" : "Live API"}</p>
      {DATA_MODE === "live" && <p className="break-all font-mono">{API_BASE_URL}</p>}
    </div>
  );
}

export function ModeBanner() {
  if (DATA_MODE === "fixture")
    return (
      <div role="status" className="mt-3 rounded-md border border-attention bg-attention-surface px-4 py-2 text-[12px] text-attention-foreground">
        <strong className="font-semibold">Fixture preview — illustrative data, not live.</strong>{" "}
        <span>Values come from approved contract fixtures. Actions that change data are disabled.</span>
      </div>
    );
  return (
    <div role="status" className="mt-3 break-all rounded-md border border-border bg-card px-4 py-2 text-xs text-muted-foreground">
      Live API · <span className="font-mono">{API_BASE_URL}</span>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex min-h-screen w-full gap-6 p-3 lg:p-5">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:bg-card focus:px-3 focus:py-1.5">Skip to content</a>
      <aside className="sticky top-5 hidden h-[calc(100vh-2.5rem)] w-56 shrink-0 flex-col rounded-xl border border-sidebar-border bg-sidebar lg:flex">
        <Brand /><Nav /><ModeFooter />
      </aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <ConsoleButton aria-label="Close menu" variant="ghost" className="absolute inset-0 h-full w-full !rounded-none !bg-background" onClick={() => setOpen(false)} />
          <aside className="relative m-3 flex h-[calc(100%-1.5rem)] w-64 flex-col rounded-xl border border-sidebar-border bg-sidebar">
            <ConsoleButton aria-label="Close menu" variant="ghost" onClick={() => setOpen(false)} className="absolute right-1 top-1 !px-2"><X className="h-4 w-4" /></ConsoleButton>
            <Brand /><Nav onNavigate={() => setOpen(false)} /><ModeFooter />
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex min-h-14 flex-wrap items-center gap-2 rounded-lg border border-sidebar-border bg-card px-3 py-2 sm:px-5">
          <ConsoleButton aria-label="Open menu" variant="ghost" onClick={() => setOpen(true)} className="!px-2 lg:hidden"><Menu className="h-4 w-4" /></ConsoleButton>
          <span className="text-xs font-semibold">InfraGuard AI</span><ChevronRight className="h-3 w-3 text-muted-foreground" aria-hidden />
          <span className="text-xs text-muted-foreground">Operations</span>
          <AppLink to="/fleet" className="ml-auto text-xs text-primary">Live fleet</AppLink>
        </header>
        <ModeBanner />
        <main id="main" className="w-full max-w-[1600px] flex-1 py-7 sm:py-8">{children}</main>
      </div>
    </div>
  );
}
