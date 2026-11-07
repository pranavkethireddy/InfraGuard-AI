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
- **Investigate.** `POST /incidents/{id}/investigate` runs the AI agent (10–30 s) and returns the updated incident. With a Gemini key it sets `explanation_source: "agent"`, and `agent_steps` lists each tool call as `{tool, summary}`. Without a key, or if the call fails, it falls back to `"rag"` and `agent_steps` is `[]`. `agent_steps` is `null` until the incident has been investigated. `maintenance_sources` holds only the records the explanation cites. Actions always need human review.
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

### Error codes

| HTTP | Codes |
|---|---|
| 404 | `ASSET_NOT_FOUND`, `INCIDENT_NOT_FOUND`, `SIMULATION_NOT_FOUND` |
| 409 | `INVALID_TRANSITION`, `SIMULATION_ALREADY_RUNNING` |
| 422 | `VALIDATION_ERROR` (FastAPI and Pydantic errors, normalized), `INVALID_FEATURES`, `INSUFFICIENT_DATA`, `UNSUPPORTED_DETECTOR` |
| 503 | `MODEL_UNAVAILABLE`, `RETRIEVAL_UNAVAILABLE`, `DATABASE_UNAVAILABLE` |

## Change process

Contract changes need a PR touching `contracts/`, a board post tagging both owners, and approval from both before merge. Additive optional fields can be merged after a board heads-up. Renames and removals bump `contract_version`.
