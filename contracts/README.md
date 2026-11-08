# InfraGuard API contract v1

**Status: proposed (issue #2).** Both owners (@pranavkethireddy for the backend, @sohaswin for the frontend) must approve on the board before either side treats this as final. After approval, the backend Pydantic models and the generated OpenAPI document are the schema authority. Each fixture in `fixtures/` must validate against them. A backend test checks this.

All numbers in fixtures are **illustrative**. They are not measured results and must never appear in the UI as real metrics.

## General rules

- Base path `/api/v1`. `/health` sits at the root.
- Timestamps are UTC ISO 8601 with a `Z` suffix, for example `2026-11-07T20:00:00Z`.
- IDs are stable strings: `cooling-01`, `pred-…`, `inc-…`, `sim-…`, `mr-…`.
- Units are encoded in field names (`temperature_c`, `fan_speed_rpm`, `air_temperature_k`).
- JSON uses `snake_case` field names.
- Contract version: `contract_version: "1"` is returned by `/health`.

## Decisions on README.md vs SKILL.md conflicts

| # | Topic | README.md | SKILL.md | Decision | Why |
|---|---|---|---|---|---|
| 1 | Routes | `/simulations`, `/maintenance/search`, `PATCH /incidents/{id}` | `/scenarios/{id}/start`, `/scenarios/{run}/events`, `/legacy/import`, `/impact/estimate`, `/incidents/{id}/approve`, `/handoff` | README routes, plus `GET /models` | Fewest routes that cover the MVP. The UI polls readings, so a separate events stream isn't needed. `/models` backs the model-card page. |
| 2 | Prediction field names | `model_name`, `risk_score`, `score_kind`, `risk_level`, `prediction_horizon_hours` | `model_id`, `score`, `score_type`, `risk_label`, `horizon_days` | README names, plus `detector_id`, `target` and `limitations` from SKILL | README names already appear in the planned UI copy. The three SKILL fields add rigor (what is predicted, known limits) at low cost. |
| 3 | Score kind enum | `heuristic`, `model_score`, `calibrated_probability` | `calibrated_probability`, `raw_model_score`, `heuristic_anomaly_score`, `rul_cycles`, `energy_residual_anomaly` | `heuristic`, `model_score`, `calibrated_probability` | The MVP has only a rule and one classifier. RUL and energy values are added when those stretch models exist. |
| 4 | Risk level enum | `low`, `medium`, `high` | `normal`, `review`, `critical`, `insufficient_data` | `low`, `medium`, `high` | Simplest three-level badge. Insufficient data becomes an error (row 7), not a level. |
| 5 | Provenance | `data_origin: simulated \| observed` | `is_synthetic: bool` | `data_origin: "simulated" \| "observed"` | One field, and it is extensible (for example a future `replay` value). AI4I rows are `simulated` because AI4I is a synthetic benchmark. |
| 6 | Incident states | `open`, `acknowledged`, `resolved` | `detected`, `investigating`, `action_proposed`, `human_approved`, `resolved` | `open`, `acknowledged`, `resolved` | Three states are enough for the demo. Allowed transitions are listed under Incidents. Anything else returns `409`. |
| 7 | Missing or unsupported input | `422` validation error | `status=insufficient_data` with `score=null` | `422` with code `INSUFFICIENT_DATA`, `INVALID_FEATURES` or `UNSUPPORTED_DETECTOR` | One error path. No prediction is returned without a real score, so a `null` score never reaches the UI. |
| 8 | Error envelope | `{error:{code,message,details,request_id}}` | `{error:{code,message,details}}` | README version, with `request_id` | The request ID helps debugging and costs nothing. |
| 9 | Horizon | `prediction_horizon_hours` | `horizon_days` | `prediction_horizon_hours`, `null` for both MVP detectors | Neither the AI4I nor the cooling rule forecasts. SKILL Phase C forbids inventing a horizon. |
| 10 | Detector IDs | `cooling-rule-v1` | `facility_anomaly_v1`, `industrial_failure_v1` | `cooling-rule-v1`, `industrial-failure-v1` | One kebab-case style, matching the README request example. |
| 11 | Impact | `estimated_downtime_cost`, `estimated_total_impact` | `expected_scenario_loss` | README formula, embedded in the incident as `impact` | README warns against calling a heuristic-based value an "expected loss". No separate `/impact/estimate` route in the MVP. |
| 12 | Backend CORS env var | `CORS_ORIGINS` | `FRONTEND_ORIGINS` | `CORS_ORIGINS` (comma-separated) | README is the setup guide. One name avoids confusion. |

## Endpoints

| Method | Route | Request fixture | Response fixture |
|---|---|---|---|
| GET | `/health` | none | `health.response.json` |
| GET | `/api/v1/assets` | none | `assets.list.response.json` |
| GET | `/api/v1/assets/{asset_id}` | none | `asset.detail.response.json` |
| GET | `/api/v1/assets/{asset_id}/readings?start=&end=&limit=` | none | `asset.readings.response.json` |
| POST | `/api/v1/readings` | `readings.request.json` | `readings.response.json` (201) |
| POST | `/api/v1/predictions` | `prediction.cooling.request.json`, `prediction.industrial.request.json` | `prediction.cooling.response.json` (triggered), `prediction.cooling.normal.response.json` (no incident), `prediction.industrial.response.json` (201, or 200 on an idempotent repeat) |
| GET | `/api/v1/models` | none | `models.list.response.json`; one evaluated entry: `model.evaluated.example.json` |
| GET | `/api/v1/incidents?status=&asset_id=&limit=&offset=` | none | `incidents.list.response.json`, `incidents.list.empty.response.json` |
| GET | `/api/v1/incidents/{incident_id}` | none | `incident.detail.response.json` (open), `incident.resolved.response.json` (resolved, with notes) |
| PATCH | `/api/v1/incidents/{incident_id}` | `incident.patch.request.json` | incident detail shape |
| POST | `/api/v1/incidents/{incident_id}/investigate` | none | `incident.investigate.response.json` (incident detail shape, 200) |
| POST | `/api/v1/simulations` | `simulation.request.json` | `simulation.response.json` (201) |
| GET | `/api/v1/simulations?status=&asset_id=&limit=&offset=` | none | `simulations.list.response.json` |
| GET | `/api/v1/simulations/{simulation_id}` | none | `simulation.status.response.json` |
| POST | `/api/v1/simulations/{simulation_id}/reset` | none | `simulation.reset.response.json` |
| POST | `/api/v1/maintenance/search` | `maintenance.search.request.json` | `maintenance.search.response.json`, `maintenance.search.no_evidence.response.json` |
| GET | `/api/v1/fleet/sites` | none | `fleet.sites.response.json` |
| GET | `/api/v1/fleet/map?site=&history=` | none | `fleet.map.response.json` |
| GET | `/api/v1/fleet/status?site=&history=&status=&hall_id=` | none | `fleet.status.response.json`, `fleet.status.mining.response.json` (examples filtered to `status=critical&history=3`) |
| GET | `/api/v1/fleet/racks/{rack_id}?history=` | none | `fleet.rack.response.json` |
| GET | `/api/v1/fleet/servers/{server_id}?history=` | none | `fleet.server.response.json` (throttling), `fleet.server.crashed.response.json` |
| GET | `/api/v1/fleet/live` | none | `fleet.live.response.json` |
| POST | `/api/v1/fleet/live/start` | `fleet.live.start.request.json` (optional body) | live status shape (200) |
| POST | `/api/v1/fleet/live/stop` | none | live status shape (200) |
| POST | `/api/v1/fleet/faults` | `fleet.faults.request.json` (optional body; default `{"count": 3}`) | `fleet.faults.response.json` (201) |
| POST | `/api/v1/fleet/clear` | none | `fleet.clear.response.json` |
| GET | `/api/v1/incidents/{id}/whatif` | none | `incident.whatif.response.json` |
| GET | `/api/v1/ops/technicians?site=` | none | `ops.technicians.response.json` |
| GET | `/api/v1/ops/plan?site=` | none | `ops.plan.response.json` |
| POST | `/api/v1/ops/dispatch` | `ops.dispatch.request.json` | `ops.dispatch.response.json` (201) |
| GET | `/api/v1/learning/matrix` | none | `learning.matrix.response.json` |
| GET | `/api/v1/learning/cases?asset_type=&site=` | none | `learning.cases.response.json` |

Error examples are in `error.422.json`, `error.404.json`, `error.409.json` and `error.503.json`.

### Lists, pagination and time filters

- Paginated lists return `{ "items": [...], "total": n, "limit": n, "offset": n }`. The default `limit` is 50 and the maximum is 200.
- An empty list is a normal `200` with `items: []` and `total: 0`, never a `404`.
- Reading history uses `start` (inclusive) and `end` (exclusive), both UTC. With no `start`, the last 24 h are returned. Results are ordered by `observed_at` ascending and capped by `limit` (default 500, max 2000).

### Predictions

- `risk_score` is a number in `[0, 1]`. `score_kind` says how to read it. A `heuristic` score must never be labelled a probability in the UI.
- `risk_level` comes from detector-specific thresholds in `configs/`. `GET /models` publishes them.
- `simulation_id` is optional on the request (`null` for non-simulated traffic) and is echoed in the response. It is how predictions and incidents are linked to a run for reset.
- **Repeated evaluation of the same reading is idempotent.** A prediction is unique per (`asset_id`, `detector_id`, `observed_at`). Posting the same one again returns the stored prediction with `200`, and incident counters don't change.
- `incident_id` is set when this prediction opened or updated an active incident, and is `null` otherwise. A below-trigger result (`prediction.cooling.normal.response.json`) has `incident_id: null`.
- `explanation_source` is `rule`, `template`, `rag` or `agent` (`agent` only on incidents, after `/investigate`). `maintenance_sources` is empty unless retrieval ran.
- Each detector has its own input schema in `readings`. Cooling and AI4I inputs are never interchangeable. Sending AI4I fields to `cooling-rule-v1` returns `422 INVALID_FEATURES`.
- An asset whose `compatible_detector` doesn't match `detector_id` returns `422 UNSUPPORTED_DETECTOR`.
- A model whose artifact isn't trained or loaded returns `503 MODEL_UNAVAILABLE`.

### Models and metrics

- `metrics` is `null` unless `evaluation_status` is `"evaluated"`. The UI shows "not evaluated" for `null`.
- When present, `metrics` is copied from `ml/artifacts/metrics/<detector_id>.json` and is never typed in by hand. Shape: `split`, `evaluated_at`, `dataset_version`, `seed`, `n`, `positives`, `threshold`, `threshold_selection`, `precision`, `recall`, `f1`, `pr_auc`, `roc_auc | null`, `brier | null`, `calibrated`, `confusion_matrix {tp, fp, tn, fn}`, `baseline {name, pr_auc, f1}`, `metrics_file`. See `model.evaluated.example.json`. Its numbers are placeholders, not results.

### Incidents

- One active (`open` or `acknowledged`) incident per (`asset_id`, `detector_id`). Each new triggering prediction (a distinct `observed_at`) updates `last_seen_at` and `prediction_count` instead of creating a new incident.
- After an incident is resolved, the cooling rule needs `cooldown_readings` below-threshold readings before it can open a new one, so the incident doesn't immediately reopen.
- An incident's `simulation_id` is taken from the prediction that opened it.
- Allowed transitions: `open → acknowledged`, `open → resolved`, `acknowledged → resolved`. Any other transition returns `409 INVALID_TRANSITION`.
- `PATCH` body: `{ "status": "acknowledged" | "resolved", "note": string | null }`. The server sets `acknowledged_at`, `resolved_at` and `resolved_by: "operator"`.
- `notes` items: `{ "note": string, "status": "open" | "acknowledged" | "resolved", "created_at": UTC }`, oldest first. `status` is the state the incident moved to when the note was written. A `PATCH` with a non-null `note` appends one.
- `impact` is computed server-side: `estimated_downtime_cost = estimated_downtime_hours × cost_per_hour`, and `estimated_total_impact = estimated_downtime_cost + estimated_repair_cost`. Its inputs and `assumptions_source` are always included. React displays these values and never recomputes them.
- Optional (additive) impact fields: `cost_per_day = cost_per_hour × 24`, and `estimated_repair_hours` (hands-on repair time). Both may be `null`. Assumptions come from `configs/impact_assumptions.json`.
- **Business case (additive).** `cost_if_it_fails` = downtime cost + unplanned repair (`estimated_total_impact`); `cost_to_fix_now` = `planned_repair_cost` (fixing it before it fails; defaults to `estimated_repair_cost`); `savings_if_fixed_now` = the difference; `return_on_repair` = savings ÷ cost to fix now (`null` when that cost is 0). Fleet summaries add `cost_if_all_fail`, `cost_to_fix_all_now` and `savings_if_fixed_now` over unresolved incidents. All are labelled demo assumptions except mining revenue (below).
- **Problem and cause (additive).** After an investigation, `problem` (one sentence: what is wrong, where) and `likely_cause` (from readings and maintenance records, or says unknown) are set; both are `null` before.
- **Investigate.** `POST /incidents/{id}/investigate` runs the AI agent (usually 1–5 s) and returns the updated incident. The backend runs every tool itself (incident, recent readings, impact, maintenance search, model card) and makes **one** Gemini request with the results, so the free tier lasts about 4× longer than a multi-turn loop. With a Gemini key it sets `explanation_source: "agent"`; `agent_steps` lists each tool as `{tool, summary}`. Without a key, or if the call fails, it falls back to `"rag"`: the same tool results fill a template. When a key is rate limited the backend moves to `GEMINI_API_KEY_2`, then to the models in `GEMINI_FALLBACK_MODELS`; it falls back to `"rag"` at once when every model and key is out of quota. `agent_steps` is `null` until the incident has been investigated. `maintenance_sources` holds only the records the explanation cites. Actions always need human review.
- **Editing impact assumptions is deferred past the MVP.** Assumptions come from `configs/` and are shown read-only. A later `PATCH /api/v1/assets/{asset_id}/impact-assumptions` would be an additive change.
- `priority_index` (0–1) combines the risk level, the asset criticality and the normalized impact using the weights in `priority_weights`. It is a ranking aid, not a financial expectation.

### Simulations

- `scenario` is `normal` or `cooling_anomaly`. The same `seed` always produces the same reading **values**. Timestamps are the real emission times.
- **Who runs it.** `POST /simulations` makes the backend start the run in a background thread, so the browser only talks to FastAPI. The sample values come from @sohaswin's generator in `simulator/`. Proposed interface: `generate(scenario: str, seed: int, asset_id: str) -> list[dict[str, float]]`, a pure function with no I/O and no clock. Each sample goes through the same services as `POST /readings` and then `POST /predictions`, with `data_origin: "simulated"` and the run's `simulation_id`.
- The same generator can run standalone from a CLI (`python -m simulator ...`) that posts to the HTTP API with a `simulation_id` it was given. This is for testing and rehearsal.
- **Cadence and duration.** One sample every `tick_seconds` (default 2, set in `configs/`). The run lasts `samples_total` samples, which is the length of the generator's list.
- **Status.** `running` until the last sample is emitted, then `completed`, with `completed_at` set. Reset sets the status to `reset` at any time. There is no separate stop: reset stops the run.
- At most one `running` simulation per asset. A second start returns `409 SIMULATION_ALREADY_RUNNING`.
- **Recovery after reload.** `GET /simulations?status=running` (or with `asset_id=`) finds the active run. `GET /simulations/{id}` returns its progress (`samples_emitted` / `samples_total`).
- **Reset.** Stops the thread, deletes the run's readings and predictions (matched by `simulation_id`), resolves its active incidents with `resolved_by: "reset"`, and clears the rule's persistence and cooldown state for that asset. The demo can then be rerun. Resetting a run that is already reset is idempotent: `200` with zero counts.

### Live fleet demo

The fleet fixtures were captured from a real backend run (fallback investigation, no Gemini key), so their numbers are real outputs of the rule and the trained models on simulated readings.

- **Sites.** Two sites share one live loop: `datacenter` (`configs/datacenter_layout.json`) and `mining`, a crypto mining farm (`configs/mining_layout.json`). `GET /fleet/map`, `GET /fleet/status` take `?site=` (default `datacenter`); `GET /fleet/sites` returns both with `summary` and `site_metrics` for a site switch. Rack ids are unique across sites, so `GET /fleet/racks/{id}` needs no site. `POST /fleet/faults` takes optional `site` to pick machines from one site only.
- **Mining farm.** 2 containers (hall `kind: "mining_container"`), rows `M1`–`M4`, 24 racks of 6 ASIC miners (`miner-01`…`miner-144`, `asset_type: "asic_miner"`) and 4 fan walls (`fanwall-m1`…`m4`, `cooling_unit`, cooling rule). Miners report `hashrate_ths`, `rated_hashrate_ths`, `chip_temp_c`, `fan_speed_rpm`, `power_w`, `hw_error_pct`. Detector `miner-rule-v1` (rule, `heuristic`; no public labelled ASIC failure dataset exists): high when hashrate < 85% of rated, chip > 85 C, fan < 1500 rpm or hardware errors > 0.5% for 3 consecutive readings; medium before that. Faults: `hashboard_failure` (one of three boards drops out: hashrate and power −⅓, errors up; stays until swapped) and `fan_failure` (fan slows, chips heat, hashrate throttles, then recovers).
- **Mining revenue (real data).** Downtime for miners and fan walls is lost mining revenue: rated hashrate (a fan wall counts every miner it cools) × the latest daily hashprice in `data/market/hashprice_daily.csv` (CloudMineCrypto open data, CC BY 4.0; refresh with the API in `data/market/README.md`). `assumptions_source` names the price and date.
- **Site metrics.** `site_metrics` is a list of `{key, label, value, unit, source}` tiles. Data center: `healthy_pct`, `drives_at_risk`, `max_supply_temp_c`. Mining: `healthy_pct`, `hashrate_phs`, `hashrate_availability_pct`, `revenue_per_day`, `revenue_lost_per_day`, `efficiency_j_per_th`, `power_kw`, `hashprice_usd_per_th_day`. `value` is `null` before the first readings.
- **Layout.** `configs/datacenter_layout.json` defines halls, rows and cooling units. The backend expands each row into racks (`A1-01`, `A1-02`, ...) and each rack into monitored drives (`drive-01`, `drive-02`, ... in hall, row and rack order). The data center has 42 machines: 4 CRAC units, 36 drives in 18 racks, and 2 AI4I benchmark machines in the plant room; the mining farm has 148. `GET /assets` lists all 190. Coordinates (`x`, `y`, `width`, `depth`, hall `width`/`depth`) are floor-grid cells (`grid_unit`); a rack's top-left corner is at (`x`, `y`).
- **Live loop.** `POST /fleet/live/start` sends one reading per machine every `tick_seconds` (default 1, from 0.2 to 10) through the normal readings and predictions path, tagged `data_origin: "simulated"` and `simulation_id` = the live `run_id`. Healthy readings vary a little so charts move. Starting while running returns the current run. `POST /fleet/live/stop` stops readings (charts freeze) and cancels active faults; data and incidents stay.
- **Faults.** `POST /fleet/faults` makes machines start failing. With `asset_ids` it targets those; otherwise it picks `count` machines with no fault and no unresolved incident, rotating cooling unit, drive, miner, machine so a demo shows each kind. It starts the live loop if needed. Faults change only the readings: `cooling_failure` (temperature up about 13 C, fan down, then recovers), `drive_degradation` (SMART error counts climb; when repaired the drive counts as hot-swapped), `machine_overstrain` (torque and tool wear up, speed down, then recovers). The cooling rule and trained models decide the risk and open the incidents, usually within 2 to 7 ticks. `simulated_fault` on a machine shows the injected fault and its `phase` (`ramping`, `holding`, `recovering`) so the demo is honest about it.
- **Automatic investigation.** With `auto_investigate` on (default), each incident the live loop opens is queued for the AI agent. `investigation_status` on the incident (and on `active_incident` in fleet views) moves `queued → running → completed` (or `failed`). It is `null` on incidents nobody queued. Results are the same as `POST /incidents/{id}/investigate`.
- **Clear.** `POST /fleet/clear` deletes every reading, prediction and incident, cancels faults and resets any running single-asset simulation. The live loop keeps running, so charts continue from a clean state. Counts in the response say what was removed.
- **Status rules.** Per machine: `critical` = unresolved high-risk incident or latest risk high; `warning` = latest risk medium or any other unresolved incident; `healthy` = latest risk low; `no_data` = nothing scored yet. Incidents stay open after a machine recovers until an operator resolves them, so the machine stays `critical` until then. A rack takes the worst status of its machines and is at least `warning` when a cooling unit in `cooled_by` is not healthy; `reasons` says why in plain text. A hall takes the worst status of its racks and machines.
- **Summary.** Each site counts only its own machines and incidents. `downtime_cost_per_day_at_risk` is the sum of `impact.cost_per_day` over unresolved incidents, from the labelled assumptions in `configs/impact_assumptions.json` (assets without their own entry use `asset_type_defaults`).
- **Single-asset simulations.** `POST /simulations` returns `409 FLEET_LIVE_RUNNING` while the live loop runs, and `POST /fleet/live/start` returns `409 SIMULATION_ALREADY_RUNNING` while a single-asset run is active.

### Operations: decide and act

Problem this solves: facilities already collect alerts and equipment data, but operators still struggle to connect symptoms, find the likely cause and decide which repair matters most financially with a small crew. InfraGuard puts investigation, choice, dispatch and learning in one incident workflow. All crew, window, price and thermal values come from `configs/operations.json` (labelled demo assumptions; people are fictional) except mining revenue, which uses the real hashprice.

- **Demo clock.** Each live tick advances a demo clock by `demo_minutes_per_tick` (2), starting at the real local time (`America/Chicago`). Durations in these responses (`*_hours`, `eta_minutes`) are demo time. A 3 h CRAC repair takes 90 ticks.
- **Faults hold until repaired.** Injected faults no longer end by themselves. A technician finishing the work order (or an operator resolving the incident) repairs it and the readings recover. Cooling and miner fan faults keep getting worse while unrepaired (3 C and 6 C per demo hour), slower while mitigated.
- **Power shutdown.** A cooling unit at or above `rack_shutdown_c` (42 C) powers off every rack it cools (back on below 40 C); a miner with chip temperature at or above 95 C powers off until repaired. Machines get `power_state` (`on`, `at_risk`, `off`), `power_reason` and `shutdown_eta_minutes` (demo minutes, from the observed trend, only for machines already past their alert level); racks get `power_state` and `shutdown_eta_minutes`; summaries count `machines_powered_off` and `machines_at_risk_of_shutdown`. A powered-off machine sends no readings and shows `critical`. Powered-off miners count as zero hashrate in the mining metrics.
- **What-if (three futures).** `GET /incidents/{id}/whatif` projects the incident forward from the latest reading and its trend (a cautious Theil–Sen slope, the 60th percentile of pairwise slopes over the last 38 readings) under: `fix_now` (soonest qualified technician; may pause their routine job; overtime outside the window), `wait_for_window` (nightly maintenance window in the data center; power-price curtailment window at the mining farm, when miners would be off anyway so repair hours lose no revenue) and `buy_time` (mitigate now: move load and boost the neighbouring cooling unit, or underclock a hot miner; repair in the window if that holds, otherwise start now). Each option has `costs` (labor, parts — planned if no shutdown, unplanned if it shuts down or the part already failed — downtime or lost revenue, mitigation, displaced work), `shutdown_at_hours`, `downtime_hours` and a `curve` (every 0.5 h for 12 h, `value` and `power_state`). `recommended` is the lowest total, with `reason`. Drive and machine models give a 30-day risk, not a failure time, so their options have no curve, `risk_note` says so, and fixing now is recommended. A heat path counts the shutdown limit as reached when the projected value plus the sensor wobble (largest swing around the trend) touches it, so `shutdown_at_hours: null` is a promise the live simulation keeps (tested). Mitigation slows the climb to 10% (data center) or 20% (miner) of the unmitigated rate.
- **Technicians.** `GET /ops/technicians` lists every technician and mechanic: `status` (`idle`, `traveling`, `working`), `location_hall_id`, `current_work_order` (with `progress` and `eta_minutes`) and queued work. Some start on routine jobs (filter changes, firmware, cleaning) that repeat.
- **Repair plan.** `GET /ops/plan?site=` ranks unresolved incidents by `savings_per_tech_hour` (`savings_if_fixed_now` / repair hours) and gives each the recommended option and a different technician; `move_from` names the routine job someone is pulled off. `status` is `ready`, `waiting_for_technician` or `dispatched`.
- **Dispatch.** `POST /ops/dispatch {incident_id, option?, technician_id?}` creates the work order (defaults: the recommended option and the technician it was priced with). A routine job is paused (`displaced`) and resumes after. Options that start later are `scheduled`. The incident becomes `acknowledged` and gets `work_order_id`; machines show `work_order`. When the work finishes, the incident is resolved with `resolved_by: "technician"`, the work order gets its actual `cost`, and the repair is learned. Errors: `404 INCIDENT_NOT_FOUND`/`TECHNICIAN_NOT_FOUND`, `409 ALREADY_DISPATCHED`/`INCIDENT_RESOLVED`/`TECHNICIAN_BUSY`/`NO_TECHNICIAN`, `422 TECHNICIAN_NOT_QUALIFIED`/`OPTION_NOT_AVAILABLE`.
- **Learning matrix.** Every finished repair, and every operator resolution with a note, becomes a learned case (`lc-…`) with symptom, cause, fix, hours, cost and outcome. Cases persist across restarts and `/fleet/clear` (`LEARNED_CASES_PATH`, default `backend/var/learned_cases.json`, not committed) and are shared across sites: an investigation of the same equipment type at any site searches them, and the AI cites them like maintenance records. `GET /learning/matrix` groups cases by equipment type and symptom with `sites_seen`, `shared_with_sites`, averages, `fixed_before_failure_pct` and `best_fix`.

### GPU servers and jobs

Problem this solves: a failing cooling unit rarely breaks anything at first. The GPUs it cools get hot and slow themselves down (throttling), and every GPU in a synchronous job waits for the slowest one, so customers quietly get less compute than they pay for. Operators see one temperature alarm and nothing about which GPUs, which job, or what it costs.

- **Layout.** Every data-center rack holds 2 drives and 4 GPU servers (`srv-<rack>-<slot>`, e.g. `srv-B1-01-2`), 8 GPUs each: 72 servers, 576 GPUs. The data center now has 114 machines (262 across both sites). `RackDetail.server_ids` lists a rack's servers; they are also in `machines`/`machine_ids`.
- **Jobs.** Each row runs one synchronous training job across all its servers (`job-A1` … `job-B2`). `FleetMap.jobs` (additive) gives each job's `pace_pct` (the slowest GPU's clock), `gpus_throttled`, `servers_down`, and `lost_usd_per_hour` = idle GPUs + slowdown of the running ones x `gpu_hour_usd` (2.50, demo assumption in `configs/datacenter_layout.json`). One stopped server or lost GPU stalls the whole job (`pace_pct` 0).
- **Readings.** A `gpu_server` reports `inlet_temp_c` (supply air of its rack's cooling unit), `online`, `gpus_online`, `gpus_throttled`, `max_gpu_temp_c`, `min_gpu_clock_pct`, `compute_pct`, `ecc_errors`, `psu_ok` (of 2), `power_w`, and `gpu1_temp_c` … `gpu8_temp_c`, `gpu1_clock_pct` … `gpu8_clock_pct`. A GPU throttles above 83 C.
- **Server detail.** `GET /fleet/servers/{id}` returns the `machine` (MachineStatus), `gpus` (8 x `index`, `temp_c`, `clock_pct`, `status`: `ok` / `throttling` / `offline` / `no_data`), `psus_ok`/`psus_total`, `inlet_temp_c`, `online`, `ecc_errors`, `power_w`, its `job` and the `cooled_by` cooling units. 404 `SERVER_NOT_FOUND` for anything that is not a GPU server.
- **Faults and detector.** New fault kinds `gpu_fault` (one GPU heats up, logs memory errors, then drops off the bus), `psu_failure` (one of two power supplies fails) and `server_crash`. Detector `server-rule-v1` (transparent rule): server not responding, a GPU off the bus or more than 10 memory errors is high risk; lost power redundancy is medium. Heat throttling is not a server fault: it is costed on the cooling unit's incident. Incident title `GPU server fault: <name>`.
- **Costs.** `gpu_server` impact uses `cost_basis: gpu_job`: `cost_per_hour` = GPUs in its job x GPU-hour price, because a stopped server stalls the whole job. A cooling incident's what-if now counts the GPU compute already being lost on the racks it cools.
- **What-if for servers.** `buy_time` = restart the job from its last checkpoint without the server, so only its own 8 GPUs are lost until the repair (`incident.server.whatif.response.json`). Dispatching it marks the server drained and the job's `lost_usd_per_hour` drops accordingly. A power-supply fault loses nothing yet; `risk_note` gives the cost if the second one fails, and waiting for the window is usually cheapest.
- **Site metrics (data center).** `gpus_throttling`, `gpu_compute_lost_per_hour` (USD/h), `gpu_jobs_full_speed`. `fleet.jobs.excerpt.json` shows jobs and metrics during a cooling failure plus a server crash.

### Technicians on the floor and the pager

Problem this solves: an alert reaches a dispatcher, who phones around to find who is free and near. InfraGuard sends the closest qualified technician the moment the incident opens, shows them walking there, and puts the job, the reason and the business case on their pager.

- **Floor plan.** `GET /ops/floor?site=` (`ops.floor.response.json`): halls side by side (`x` offset, `GAP` 2 cells), a door per hall on the corridor (`corridor_y`) and a service lane `lane_offset` cells in from each hall's left wall. A hall-local point from the fleet map is at (`hall.x + x`, `y`).
- **Walking.** Technicians have a live `position` (FloorPoint: `x`, `y`, `hall_id`, None in the corridor), the `path` still to walk (waypoints, empty when not walking) and `walking_minutes_left`. They walk at `walk_cells_per_demo_minute` (2.0, demo pace including picking up tools) along lane → door → corridor → door → lane → work spot. Travel time is that walking time (the fixed 10 min travel is gone). Each work order has a `spot` (the aisle in front of the rack, or beside the unit) and `asset_name`.
- **Closest technician.** Dispatch without a `technician_id` sends the qualified technician who can start soonest (walking time, or after their current repair), unless the chosen option starts later (the window), when the technician it was priced with is kept. `PagerJob.why_you` says why ("Closest qualified technician: about 6 demo minutes away.").
- **Automatic dispatch.** When the live loop opens an incident, it is dispatched at once with the recommended option to the closest qualified technician. `TechniciansResponse.auto_dispatch` shows it; `POST /ops/auto-dispatch {enabled}` switches it (default on; `AUTO_DISPATCH=false` in the environment starts it off).
- **Pager (iPad).** `POST /ops/pager/{technician_id}/claim` makes the technician device-controlled (`device_controlled: true`); `/release` hands them back to the simulation. `GET /ops/pager/{technician_id}` returns `PagerView`: `technician`, `job` (current repair: `work_order`, asset, location, problem, likely cause, `steps`, `why_you`, `savings_if_fixed_now`, `cost_per_hour_while_down`, `walking_minutes_left`, allowed `actions`), `queue` (scheduled repairs), `demo_time` and `version`. For a device-controlled technician a repair starts as `paged` (actions `accept`, `decline`); `accept` starts the walk; when the planned hours are used up it waits as `awaiting_confirmation` (action `done`); `done` is also allowed earlier and bills the hours actually worked (at least 0.25 h). `decline` closes the work order ("declined by …") and dispatches the incident to the next closest qualified technician. `POST /ops/pager/{technician_id}/action {action, work_order_id}`; errors 409 `NOT_YOUR_JOB`, `NOT_PAGED`, `NOT_STARTED`. Fixtures: `ops.pager.claim.response.json`, `ops.pager.paged.response.json`, `ops.pager.walking.response.json`, `ops.pager.action.request.json`.
- **Live stream (low latency).** `GET /ops/stream?technician_id=` is server-sent events: `event: pager` with a PagerView whenever it changes (checked every 0.2 s), and a `: ping` comment every 15 s. Without `technician_id`: `event: crew` with `GET /ops/technicians?site=` for the map. `max_seconds` (default 3600) ends the stream; browsers reconnect automatically. Example: `ops.stream.pager.example.txt`. Use `EventSource` instead of polling.
- **New work statuses.** `WorkStatus` adds `paged` and `awaiting_confirmation`.
- **iPad on the same Wi-Fi.** Run the backend with `--host 0.0.0.0` and add the frontend's LAN origin (e.g. `http://192.168.1.20:5173`) to `CORS_ORIGINS`; point the pager page's API base at `http://<laptop LAN IP>:8000`.

### Error codes

| HTTP | Codes |
|---|---|
| 404 | `ASSET_NOT_FOUND`, `INCIDENT_NOT_FOUND`, `SIMULATION_NOT_FOUND`, `RACK_NOT_FOUND`, `TECHNICIAN_NOT_FOUND` |
| 409 | `INVALID_TRANSITION`, `SIMULATION_ALREADY_RUNNING`, `FLEET_LIVE_RUNNING`, `FAULT_ALREADY_ACTIVE`, `NO_HEALTHY_ASSETS`, `ALREADY_DISPATCHED`, `INCIDENT_RESOLVED`, `TECHNICIAN_BUSY`, `NO_TECHNICIAN` |
| 422 | `VALIDATION_ERROR` (FastAPI and Pydantic errors, normalized), `INVALID_FEATURES`, `INSUFFICIENT_DATA`, `UNSUPPORTED_DETECTOR`, `TECHNICIAN_NOT_QUALIFIED`, `OPTION_NOT_AVAILABLE` |
| 503 | `MODEL_UNAVAILABLE`, `RETRIEVAL_UNAVAILABLE`, `DATABASE_UNAVAILABLE`, `SIMULATOR_UNAVAILABLE` |

## Change process

Contract changes need a PR touching `contracts/`, a board post tagging both owners, and approval from both before merge. Additive optional fields can be merged after a board heads-up. Renames and removals bump `contract_version`.
