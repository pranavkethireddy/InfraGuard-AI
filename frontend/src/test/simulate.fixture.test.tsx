import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import * as client from "@/api/client";
import { SimulatePage } from "@/pages/SimulatePage";

describe("SimulatePage (fixture mode)", () => {
  it("form submission does not mutate and shows a static, labelled status", async () => {
    expect(client.DATA_MODE).toBe("fixture");
    const spy = vi.spyOn(client.api, "startSimulation");
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={qc}><SimulatePage /></QueryClientProvider>);
    const form = await screen.findByRole("form", { name: "Start simulation" });
    expect(screen.getByRole("button", { name: /start simulation/i })).toBeDisabled();
    fireEvent.submit(form);
    expect(spy).not.toHaveBeenCalled();
    expect(screen.getByText("Static fixture — not running")).toBeInTheDocument();
    expect(screen.getByText("sim-demo-001")).toBeInTheDocument();
  });
});
