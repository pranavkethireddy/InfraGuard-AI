import { NavLink, Route, Routes, useParams, useSearchParams } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { RouterAdapterProvider, type AppLinkProps, type RouterAdapter } from "@/lib/router-adapter";
import { OverviewPage } from "@/pages/OverviewPage";
import { AssetsPage } from "@/pages/AssetsPage";
import { AssetDetailPage, NotFoundState } from "@/pages/AssetDetailPage";
import { SimulatePage } from "@/pages/SimulatePage";
import { IncidentsPage } from "@/pages/IncidentsPage";
import { IncidentDetailPage } from "@/pages/IncidentDetailPage";
import { ModelsPage } from "@/pages/ModelsPage";
import { FleetPage } from '@/pages/FleetPage';
import { OperationsPage } from '@/pages/OperationsPage';

function RRLink({ to, className = "", activeClassName, exact, onClick, children }: AppLinkProps) {
  return (
    <NavLink to={to} end={exact} onClick={onClick}
      className={({ isActive }) => (isActive && activeClassName ? `${className} ${activeClassName}` : className)}>
      {children}
    </NavLink>
  );
}
const adapter: RouterAdapter = { Link: RRLink };

function AssetDetailRoute() {
  return <AssetDetailPage id={useParams().id ?? ""} />;
}
function IncidentDetailRoute() {
  return <IncidentDetailPage id={useParams().id ?? ""} />;
}
function FleetRoute() {
  const [search, setSearch] = useSearchParams();
  const site = search.get('site') === 'mining' ? 'mining' : 'datacenter';
  return <FleetPage site={site} onSiteChange={(next) => setSearch((prev) => { const p = new URLSearchParams(prev); p.set('site', next); return p; })} />;
}
function OverviewRoute() {
  const [search, setSearch] = useSearchParams();
  const site = search.get('site') === 'mining' ? 'mining' : 'datacenter';
  return <OverviewPage site={site} onSiteChange={(next) => setSearch((prev) => { const p = new URLSearchParams(prev); p.set('site', next); return p; })} />;
}
function OperationsRoute() {
  const [search, setSearch] = useSearchParams();
  const site = search.get('site') === 'mining' ? 'mining' : 'datacenter';
  return <OperationsPage site={site} onSiteChange={(next) => setSearch((prev) => { const p = new URLSearchParams(prev); p.set('site', next); return p; })} />;
}

export function App() {
  return (
    <RouterAdapterProvider value={adapter}>
      <AppShell>
        <Routes>
          <Route path="/" element={<OverviewRoute />} />
          <Route path="/fleet" element={<FleetRoute />} />
          <Route path="/operations" element={<OperationsRoute />} />
          <Route path="/assets" element={<AssetsPage />} />
          <Route path="/assets/:id" element={<AssetDetailRoute />} />
          <Route path="/simulate" element={<SimulatePage />} />
          <Route path="/incidents" element={<IncidentsPage />} />
          <Route path="/incidents/:id" element={<IncidentDetailRoute />} />
          <Route path="/models" element={<ModelsPage />} />
          <Route path="*" element={<NotFoundState what="Page" back="/" backLabel="Go to overview" />} />
        </Routes>
      </AppShell>
    </RouterAdapterProvider>
  );
}
