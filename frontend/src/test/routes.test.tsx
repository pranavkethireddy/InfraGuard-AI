import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { App } from "@/App";
function LocationProbe() { const location = useLocation(); return <output aria-label="Current URL">{location.pathname}{location.search}</output>; }

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}><App /><LocationProbe /></MemoryRouter></QueryClientProvider>,
  );
}

describe("routes (react-router-dom)", () => {
  it.each([
    ["/", "Overview"], ["/fleet", "Live fleet"], ["/assets", "Assets"], ["/simulate", "Simulate"], ["/incidents", "Incidents"], ["/models", "Models"],
    ["/assets/cooling-01", "CRAC Unit 1"], ["/incidents/inc-demo-001", "Sustained high temperature on CRAC Unit 1"],
  ])("%s renders %s heading", async (path, heading) => {
    renderAt(path);
    expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
  });
  it("incident workspace shows the backend impact total and disables mutations in fixture mode", async () => {
    renderAt("/incidents/inc-demo-001");
    expect(await screen.findByText("$51,500")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark resolved" })).toBeDisabled();
  });
  it("shows not-found for an unknown incident and unknown page", async () => {
    renderAt("/incidents/nope");
    expect(await screen.findByText(/not found/)).toBeInTheDocument();
    renderAt("/nowhere");
    expect(await screen.findByText("Page not found")).toBeInTheDocument();
  });
  it("always shows the fixture banner in fixture mode", () => {
    renderAt("/");
    expect(screen.getByText("Fixture preview — illustrative data, not live.")).toBeInTheDocument();
  });
  it('persists fleet site selection in the URL and restores mining from a direct URL', async () => {
    renderAt('/fleet?site=mining');
    expect(screen.getByRole('tab', { name: 'Crypto mining site' })).toHaveAttribute('aria-selected', 'true');
    fireEvent.click(screen.getByRole('tab', { name: 'Data center' }));
    await waitFor(() => expect(screen.getByLabelText('Current URL')).toHaveTextContent('/fleet?site=datacenter'));
  });
});
