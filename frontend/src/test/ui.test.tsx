import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ModelCard } from "@/components/ModelCard";
import { OriginBadge, ScoreValue } from "@/components/ui-kit";
import { allowedTransitions, ImpactLedger } from "@/pages/IncidentDetailPage";
import { parseSeed } from "@/pages/SimulatePage";
import { fixtures } from "@/api/fixtures";
import evaluatedExample from "@/api/fixtures/contracts/model.evaluated.example.json";
import type { DetectorModel } from "@/api/types";

const [rule, ml] = fixtures.modelsList.items as [DetectorModel, DetectorModel];

describe("UI contract", () => {
  it("keeps synthetic source collapsed while retaining Not evaluated and no metrics", () => {
    render(<ModelCard model={ml} />);
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(screen.getAllByText("Not evaluated").length).toBeGreaterThan(0);
    const disclosure = screen.getByText(/Synthetic benchmark data;/);
    expect(disclosure).not.toBeVisible();
    fireEvent.click(screen.getByText("Source details", { selector: "summary" }));
    expect(disclosure).toBeVisible();
    expect(screen.getByText(`Source dataset: ${ml.source_dataset}`)).toBeVisible();
    expect(screen.queryByLabelText("Evaluation metrics")).toBeNull();
    expect(screen.getByText("No evaluation metrics returned by the API.")).toBeInTheDocument();
  });

  it("shows rule detector config with approved rule keys", () => {
    render(<ModelCard model={rule} />);
    expect(screen.getByText("Available")).toBeInTheDocument();
    for (const k of ["temperature_threshold_c", "consecutive_readings", "cooldown_readings"]) expect(screen.getByText(k)).toBeInTheDocument();
    expect(screen.getByText("Not applicable (rule)", { selector: "dd" })).toBeInTheDocument();
  });

  it("lists the required industrial 'type' input", () => {
    render(<ModelCard model={ml} />);
    const row = screen.getByText("type", { selector: "td" }).closest("tr")!;
    expect(within(row).getByText("Required")).toBeInTheDocument();
  });

  it("renders the evaluated example's structured metrics verbatim (test-only fixture)", () => {
    render(<ModelCard model={evaluatedExample as unknown as DetectorModel} />);
    const m = screen.getByLabelText("Evaluation metrics");
    expect(within(m).getByText("tp 34")).toBeInTheDocument();
    expect(within(m).getByText("tn 1898")).toBeInTheDocument();
    expect(within(m).getByText("No — scores are not probabilities")).toBeInTheDocument();
    expect(within(m).getByText(/majority_class/)).toBeInTheDocument();
  });

  it("keeps data_origin inspectable without a visible simulated badge", () => {
    render(<OriginBadge origin="simulated" />);
    expect(screen.queryByText("Simulated data")).toBeNull();
    expect(screen.getByText("data_origin: simulated")).not.toBeVisible();
    fireEvent.click(screen.getByText("Source details", { selector: "summary" }));
    expect(screen.getByText("data_origin: simulated")).toBeVisible();
  });

  it("labels heuristic score as not a probability and shows the raw value", () => {
    render(<ScoreValue score={0.8} kind="heuristic" />);
    expect(screen.getByText("0.8")).toBeInTheDocument();
    expect(screen.getByText(/not a probability/)).toBeInTheDocument();
    expect(screen.queryByText("80%")).toBeNull();
  });

  it("impact ledger shows backend totals exactly", () => {
    render(<ImpactLedger impact={fixtures.incidentDetail.impact!} />);
    expect(screen.getByText("$51,500")).toBeInTheDocument();
    expect(screen.getByText("$48,000")).toBeInTheDocument();
    const source = screen.getByText(`assumptions_source: ${fixtures.incidentDetail.impact?.assumptions_source}`);
    expect(source).not.toBeVisible();
    expect(screen.getByText(/scenario estimates; not measured/)).not.toBeVisible();
    fireEvent.click(screen.getByText("Source details", { selector: "summary" }));
    expect(source).toBeVisible();
    expect(screen.getByText(/scenario estimates; not measured/)).toBeVisible();
  });

  it("only allows contract incident transitions", () => {
    expect(allowedTransitions("open")).toEqual(["acknowledged", "resolved"]);
    expect(allowedTransitions("acknowledged")).toEqual(["resolved"]);
    expect(allowedTransitions("resolved")).toEqual([]);
  });

  it("accepts only integer seeds", () => {
    expect(parseSeed("42")).toBe(42);
    expect(parseSeed("4.2")).toBeNull();
    expect(parseSeed("abc")).toBeNull();
  });
});
