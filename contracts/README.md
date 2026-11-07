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
| POST | `/api/v1/predictions` | `prediction.cooling.request.json`, `prediction.industrial.request.json` | `prediction.cooling.response.json`, `prediction.industrial.response.json` (201) |
| GET | `/api/v1/models` | none | `models.list.response.json` |
| GET | `/api/v1/incidents?status=&asset_id=&limit=&offset=` | none | `incidents.list.response.json` |
| GET | `/api/v1/incidents/{incident_id}` | none | `incident.detail.response.json` |
| PATCH | `/api/v1/incidents/{incident_id}` | `incident.patch.request.json` | `incident.detail.response.json` shape |
| POST | `/api/v1/simulations` | `simulation.request.json` | `simulation.response.json` (201) |
| POST | `/api/v1/simulations/{simulation_id}/reset` | none | `simulation.reset.response.json` |
| POST | `/api/v1/maintenance/search` | `maintenance.search.request.json` | `maintenance.search.response.json` |

Error examples are in `error.422.json`, `error.404.json`, `error.409.json` and `error.503.json`.

### Lists, pagination and time filters

- Paginated lists return `{ "items": [...], "total": n, "limit": n, "offset": n }`. The default `limit` is 50 and the maximum is 200.
- Reading history uses `start` (inclusive) and `end` (exclusive), both UTC. With no `start`, the last 24 h are returned. Results are ordered by `observed_at` ascending and capped by `limit` (default 500, max 2000).

### Predictions

- `risk_score` is a number in `[0, 1]`. `score_kind` says how to read it. A `heuristic` score must never be labelled a probability in the UI.
- `risk_level` comes from detector-specific thresholds in `configs/`. `GET /models` publishes them.
- `incident_id` is set when this prediction opened or updated an active incident, and is `null` otherwise.
- `explanation_source` is `rule`, `template` or `rag`. `maintenance_sources` is empty unless retrieval ran.
- Each detector has its own input schema in `readings`. Cooling and AI4I inputs are never interchangeable. Sending AI4I fields to `cooling-rule-v1` returns `422 INVALID_FEATURES`.
- An asset whose `compatible_detector` doesn't match `detector_id` returns `422 UNSUPPORTED_DETECTOR`.
- A model whose artifact isn't trained or loaded returns `503 MODEL_UNAVAILABLE`.

### Incidents

- One active (`open` or `acknowledged`) incident per (`asset_id`, `detector_id`). Repeated triggering predictions update `last_seen_at` and `prediction_count` instead of creating new incidents.
- Allowed transitions: `open → acknowledged`, `open → resolved`, `acknowledged → resolved`. Any other transition returns `409 INVALID_TRANSITION`.
- `PATCH` body: `{ "status": "acknowledged" | "resolved", "note": string | null }`. The server sets `acknowledged_at` and `resolved_at`.
- `impact` is computed server-side: `estimated_downtime_cost = estimated_downtime_hours × cost_per_hour`, and `estimated_total_impact = estimated_downtime_cost + estimated_repair_cost`. Its inputs and `assumptions_source` are always included. React displays these values and never recomputes them.
- `priority_index` (0–1) combines the risk level, the asset criticality and the normalized impact using the weights in `priority_weights`. It is a ranking aid, not a financial expectation.

### Simulations

- `scenario` is `normal` or `cooling_anomaly`. The same `seed` always produces the same readings.
- The simulator (owned by @sohaswin) posts readings through `POST /readings`, then calls `POST /predictions`. Simulations use the same validation and incident path as any other reading.
- Reset stops the run, deletes that run's readings and predictions, resolves its incidents with `resolved_by: "reset"`, and clears detector persistence counters, so the demo can be rerun.

### Error codes

| HTTP | Codes |
|---|---|
| 404 | `ASSET_NOT_FOUND`, `INCIDENT_NOT_FOUND`, `SIMULATION_NOT_FOUND` |
| 409 | `INVALID_TRANSITION`, `SIMULATION_ALREADY_RUNNING` |
| 422 | `VALIDATION_ERROR` (FastAPI and Pydantic errors, normalized), `INVALID_FEATURES`, `INSUFFICIENT_DATA`, `UNSUPPORTED_DETECTOR` |
| 503 | `MODEL_UNAVAILABLE`, `RETRIEVAL_UNAVAILABLE`, `DATABASE_UNAVAILABLE` |

## Change process

Contract changes need a PR touching `contracts/`, a board post tagging both owners, and approval from both before merge. Additive optional fields can be merged after a board heads-up. Renames and removals bump `contract_version`.
