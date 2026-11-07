import { NavLink, Route, Routes, useParams } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { RouterAdapterProvider, type AppLinkProps, type RouterAdapter } from "@/lib/router-adapter";
import { OverviewPage } from "@/pages/OverviewPage";
import { AssetsPage } from "@/pages/AssetsPage";
import { AssetDetailPage, NotFoundState } from "@/pages/AssetDetailPage";
import { SimulatePage } from "@/pages/SimulatePage";
import { IncidentsPage } from "@/pages/IncidentsPage";
import { IncidentDetailPage } from "@/pages/IncidentDetailPage";
import { ModelsPage } from "@/pages/ModelsPage";

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

export function App() {
  return (
    <RouterAdapterProvider value={adapter}>
      <AppShell>
        <Routes>
          <Route path="/" element={<OverviewPage />} />
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
