import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, DATA_MODE, FIXTURE_MUTATION_MESSAGE } from "@/api/client";
import { fixtures } from "@/api/fixtures";
import {
  assetsQuery, modelsQuery, readingsQuery, runningSimulationsQuery, simulationPollInterval, simulationQuery, useResetSimulation, useStartSimulation,
} from "@/api/queries";
import type { Scenario, Simulation, SimulationReset } from "@/api/types";
import { ReadingsChart } from "@/components/ReadingsChart";
import {
  Badge, Empty, ErrorMessage, ErrorState, Fields, Loading, Mono, OriginBadge, PageHeader, Section, btnOutline, btnPrimary, dt, inputCls,
} from "@/components/ui-kit";

export const SIM_DETECTOR = "cooling-rule-v1";

export function parseSeed(raw: string): number | null {
  if (!/^\d+$/.test(raw.trim())) return null;
  const n = Number(raw);
  return Number.isSafeInteger(n) ? n : null;
}

function SimulationStatus({ sim, staticNote }: { sim: Simulation; staticNote?: boolean }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5">
        <Badge tone={sim.status === "running" && !staticNote ? "accent" : "neutral"}>Status: {sim.status}</Badge>
        <OriginBadge origin={sim.data_origin} />
        {staticNote && <Badge tone="attention">Static fixture — not running</Badge>}
      </div>
      <Fields rows={[
        ["Simulation", <Mono>{sim.simulation_id}</Mono>],
        ["Scenario", <Mono>{sim.scenario}</Mono>],
        ["Asset", <Mono>{sim.asset_id}</Mono>],
        ["Seed", <Mono>{sim.seed}</Mono>],
        ["Samples", <Mono>{sim.samples_emitted} / {sim.samples_total}</Mono>],
        ["Tick", <Mono>{sim.tick_seconds} s</Mono>],
        ["Started", <Mono>{dt(sim.started_at)}</Mono>],
        ["Completed", <Mono>{dt(sim.completed_at)}</Mono>],
      ]} />
      <div role="progressbar" aria-label="Samples emitted" aria-valuemin={0} aria-valuemax={sim.samples_total} aria-valuenow={sim.samples_emitted} className="h-1.5 w-full bg-muted">
        <div className="h-full bg-primary" style={{ width: `${sim.samples_total ? (sim.samples_emitted / sim.samples_total) * 100 : 0}%` }} />
      </div>
    </div>
  );
}

function ResetSummary({ r }: { r: SimulationReset }) {
  return (
    <div role="status" className="border-l-2 border-primary bg-accent/40 p-2">
      <p className="text-[13px] font-medium">Simulation <Mono>{r.simulation_id}</Mono> reset.</p>
      <Fields rows={[
        ["Readings deleted", <Mono>{r.readings_deleted}</Mono>],
        ["Predictions deleted", <Mono>{r.predictions_deleted}</Mono>],
        ["Incidents resolved", <Mono>{r.incidents_resolved}</Mono>],
      ]} />
    </div>
  );
}

export function SimulatePage() {
  const fixture = DATA_MODE === "fixture";
  const qc = useQueryClient();
  const assets = useQuery(assetsQuery());
  const models = useQuery(modelsQuery());
  const compatible = assets.data?.items.filter((a) => a.compatible_detector === SIM_DETECTOR) ?? [];
  const [assetChoice, setAssetChoice] = useState<string | null>(null);
  const assetId = assetChoice ?? compatible[0]?.asset_id ?? "";
  const [scenario, setScenario] = useState<Scenario>("cooling_anomaly");
  const [seedRaw, setSeedRaw] = useState("42");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [lastReset, setLastReset] = useState<SimulationReset | null>(null);
  const seed = parseSeed(seedRaw);

  // Recovery after reload: ask the backend which simulation is running for this asset.
  const recovery = useQuery({ ...runningSimulationsQuery(assetId), enabled: !fixture && !!assetId });
  const activeId = selectedId ?? recovery.data?.items[0]?.simulation_id ?? null;
  const sim = useQuery({ ...simulationQuery(activeId ?? ""), enabled: !fixture && !!activeId });
  const running = sim.data?.status === "running";
  const readings = useQuery({
    ...readingsQuery(assetId, 200),
    enabled: !fixture && !!assetId && !!sim.data,
    refetchInterval: simulationPollInterval(sim.data?.status),
  });
  const start = useStartSimulation();
  const reset = useResetSimulation();
  const conflict = start.error instanceof ApiError && start.error.status === 409;
  const threshold = models.data?.items.find((m) => m.detector_id === SIM_DETECTOR)?.rule_config?.temperature_threshold_c ?? null;

  const recovering = !fixture && !!assetId && recovery.isLoading;
  const startDisabledReason =
    fixture ? "Fixture preview" :
    !assetId ? "No compatible asset" :
    recovering ? "Checking for a running simulation…" :
    recovery.error ? "Could not check for a running simulation" :
    activeId && sim.isLoading ? "Loading recovered simulation…" :
    running ? "A simulation is running" :
    reset.isPending ? "Resetting…" :
    start.isPending ? "Starting…" :
    seed === null ? "Seed must be a whole number ≥ 0" : null;

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (fixture || startDisabledReason || seed === null) return;
    setLastReset(null);
    start.mutate({ scenario, asset_id: assetId, seed }, {
      onSuccess: (s) => setSelectedId(s.simulation_id),
      onError: (err) => {
        if (err instanceof ApiError && err.status === 409) {
          setSelectedId(null);
          void qc.refetchQueries({ queryKey: ["simulations", "running", assetId] });
        }
      },
    });
  }

  return (
    <>
      <PageHeader title="Simulate" meta={`Backend-run scenarios for ${SIM_DETECTOR} assets. The backend owns the runner; this page only starts, polls and resets.`} />
      {fixture && (
        <div role="note" className="mb-4 border border-attention/40 border-l-2 border-l-attention bg-attention-surface p-2.5 text-[13px] text-attention-foreground">
          {FIXTURE_MUTATION_MESSAGE} No live progress is shown in fixture preview.
        </div>
      )}
      <div className="grid gap-4 xl:grid-cols-[minmax(18rem,1fr)_2fr]">
        <Section title="Scenario">
          {assets.isLoading ? <Loading label="Loading assets…" /> : assets.error ? <ErrorState error={assets.error} title="Could not load assets" />
            : compatible.length === 0 ? <Empty>No assets compatible with {SIM_DETECTOR}.</Empty> : (
            <form className="space-y-3" onSubmit={onSubmit} aria-label="Start simulation">
              <label className="block text-[13px]"><span className="text-muted-foreground">Asset</span>
                <select className={`${inputCls} mt-1`} value={assetId} onChange={(e) => { setAssetChoice(e.target.value); setSelectedId(null); }}>
                  {compatible.map((a) => <option key={a.asset_id} value={a.asset_id}>{a.name} ({a.asset_id})</option>)}
                </select>
              </label>
              <fieldset className="text-[13px]"><legend className="text-muted-foreground">Scenario</legend>
                <div className="mt-1 flex gap-4">
                  {(["normal", "cooling_anomaly"] as const).map((s) => (
                    <label key={s} className="flex items-center gap-1.5 font-mono text-[12.5px]"><input type="radio" name="scenario" checked={scenario === s} onChange={() => setScenario(s)} />{s}</label>
                  ))}
                </div>
              </fieldset>
              <label className="block text-[13px]"><span className="text-muted-foreground">Seed (whole number ≥ 0)</span>
                <input className={`${inputCls} mt-1 font-mono`} inputMode="numeric" value={seedRaw} onChange={(e) => setSeedRaw(e.target.value)}
                  aria-invalid={seed === null} aria-describedby="seed-help" />
                <span id="seed-help" className={`mt-1 block text-xs ${seed === null ? "text-destructive" : "text-muted-foreground"}`}>
                  {seed === null ? "Seed must be a whole number of 0 or more." : "Same seed reproduces the same run."}
                </span>
              </label>
              <div className="flex items-center gap-3">
                <button type="submit" className={btnPrimary} disabled={!!startDisabledReason}>{start.isPending ? "Starting…" : "Start simulation"}</button>
                {startDisabledReason && !fixture && <span className="text-xs text-muted-foreground">{startDisabledReason}</span>}
              </div>
              {conflict && <p role="alert" className="text-[13px] text-attention-foreground">A simulation is already running for this asset. Showing it alongside.</p>}
              {start.error && !conflict && <div role="alert" className="border-l-2 border-destructive pl-2"><ErrorMessage error={start.error} /></div>}
            </form>
          )}
        </Section>

        <div className="space-y-4">
          <Section title="Current simulation">
            {fixture ? (
              <>
                <p className="mb-3 text-[13px] text-muted-foreground">Example status response from the contract fixtures:</p>
                <SimulationStatus sim={fixtures.simulationStatus} staticNote />
              </>
            ) : recovering ? <Loading label="Checking for a running simulation…" />
              : recovery.error ? <ErrorState error={recovery.error} title="Could not check for a running simulation" />
              : !activeId ? (lastReset ? <ResetSummary r={lastReset} /> : <Empty>No simulation running for this asset.</Empty>)
              : sim.isLoading ? <Loading label="Loading simulation…" />
              : sim.error ? <ErrorState error={sim.error} title="Could not load simulation status" />
              : sim.data && (
                <div className="space-y-3">
                  <SimulationStatus sim={sim.data} />
                  {sim.data.status !== "reset" && (
                    <button className={btnOutline} disabled={reset.isPending}
                      onClick={() => reset.mutate(sim.data!.simulation_id, { onSuccess: (r) => { setLastReset(r); setSelectedId(null); } })}>
                      {reset.isPending ? "Resetting…" : "Reset simulation"}
                    </button>
                  )}
                  {reset.error && <div role="alert" className="border-l-2 border-destructive pl-2"><ErrorMessage error={reset.error} /></div>}
                </div>
              )}
          </Section>

          <Section title="Backend readings" aside={readings.data && <Mono>{readings.data.total} readings{running ? " · polling" : ""}</Mono>}>
            {fixture ? <Empty>Readings are polled from the backend in live mode only.</Empty>
              : !sim.data ? <Empty>Start or recover a simulation to see readings.</Empty>
              : readings.isLoading ? <Loading /> : readings.error ? <ErrorState error={readings.error} />
              : readings.data?.items.length ? <ReadingsChart readings={readings.data.items} threshold={threshold} height={220} />
              : <Empty>No readings emitted yet.</Empty>}
          </Section>
        </div>
      </div>
    </>
  );
}
