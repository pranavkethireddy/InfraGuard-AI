# InfraGuard simulator

Python 3.11+, standard library only. Run commands from the repository root.

```python
from simulator import generate
samples = generate("cooling_anomaly", seed=42, asset_id="cooling-01")
```

`generate(scenario, seed, asset_id)` is the agreed pure interface. It returns 30
fresh dictionaries containing `temperature_c` and `fan_speed_rpm`, with no clock,
network, files, global random state, risk scores, or incident calculations.
Seeds must be non-negative integers. IDs must be non-empty strings; the backend
checks asset compatibility. Asset identity does not change the seeded values.

| Scenario | Synthetic behavior |
|---|---|
| `normal` | 30 samples near 24.5 °C and 1150 rpm, with small seeded noise |
| `cooling_anomaly` | 6 baseline samples, 18 gradually rising toward 36.5 °C with fan speed falling toward 800 rpm, then 6 recovered samples |

These values are demo assumptions, not physical validation or facility safety
limits. Under the agreed 32 °C / 3-reading rule, the anomaly includes a sustained
above-threshold segment and a recovery segment for cooldown. The generator does
not implement that detector or claim ML accuracy. At the backend's default
2-second cadence, 30 samples take about one minute (first-emission timing is
owned by the runner).

## Preview without a backend

```bash
python3 -m simulator preview --scenario cooling_anomaly --seed 42 --start-at 2026-11-07T20:00:00Z
python3 -m unittest discover -s simulator/tests -v
```

The preview is a `POST /api/v1/readings`-shaped JSON batch, with `data_origin:
"simulated"` and `simulation_id` at batch level, inherited by each reading under
contract v1. It is printed, never sent. Its timestamps come from the explicit
start argument. Use `readings_payload(...)` for the same pure envelope helper.
The same inputs recreate the exact values, so repeated generation resets all
generator state without touching global RNG state.

## Backend-managed runs

```bash
python3 -m simulator start --scenario cooling_anomaly --seed 42
python3 -m simulator status SIMULATION_ID
python3 -m simulator reset SIMULATION_ID
# Alternate API location (global option goes before the subcommand):
python3 -m simulator --base-url http://localhost:8000/api/v1 start --scenario normal
```

These commands use the agreed `/simulations` endpoints. They require Pranav's
simulation lifecycle implementation; the initial backend skeleton does not yet
provide it. Failures are reported with HTTP status, backend error code and
request ID when present, rather than silently simulating success.

The backend calls `generate`, assigns real UTC emission timestamps and simulated
provenance, and passes each sample through the same services as `/readings` and
`/predictions`, carrying the run's ID. It owns persistence, deduplication,
cooldown, progress, cancellation, and idempotent persisted reset. Reset stops
emission and clears that run's readings/predictions and detector state according
to `contracts/README.md`; this package never deletes backend state directly.

There is deliberately no second HTTP replay producer for an already running
backend simulation: feeding both would double the readings. A standalone ingest
runner needs an agreed externally-managed run lifecycle first. Reading values
are deterministic; real backend emission timestamps are not.
