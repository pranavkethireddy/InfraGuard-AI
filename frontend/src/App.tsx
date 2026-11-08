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
import { ServerPage } from '@/pages/ServerPage';
import { PagerPage } from '@/pages/PagerPage';
import { ComponentPage } from '@/pages/ComponentPage';
import { RackPage } from '@/pages/RackPage';

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
function ServerRoute() {
  const id = useParams().id ?? ''; const [search, setSearch] = useSearchParams();
  const raw = search.get('gpu'); const index = raw == null ? undefined : Number(raw);
  return <ServerPage id={id} gpuIndex={index !== undefined && Number.isSafeInteger(index) && index >= 0 ? index : undefined} onGpuChange={(gpu) => setSearch((prev) => { const p = new URLSearchParams(prev); p.set('gpu', String(gpu)); return p; })} />;
}
function PagerRoute() {
  const [search, setSearch] = useSearchParams();
  return <PagerPage technicianId={search.get('technician') || 'tech-03'} onTechnicianChange={(id) => setSearch((prev) => { const p = new URLSearchParams(prev); p.set('technician', id); return p; })} />;
}
function ComponentRoute() { const { id, cid } = useParams(); return <ComponentPage id={id ?? ''} cid={cid ?? ''} />; }
function RackRoute() { return <RackPage id={useParams().id ?? ''} />; }

export function App() {
  return (
    <RouterAdapterProvider value={adapter}>
      <AppShell>
        <Routes>
          <Route path="/" element={<OverviewRoute />} />
          <Route path="/fleet" element={<FleetRoute />} />
          <Route path="/operations" element={<OperationsRoute />} />
          <Route path="/pager" element={<PagerRoute />} />
          <Route path="/servers/:id" element={<ServerRoute />} />
          <Route path="/fleet/servers/:id" element={<ServerRoute />} />
          <Route path="/fleet/servers/:id/components/:cid" element={<ComponentRoute />} />
          <Route path="/fleet/racks/:id" element={<RackRoute />} />
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
