---
name: infraguard-multimodel-ml
summary: Build a React + TypeScript frontend and Python FastAPI backend integrating rigorously validated separate equipment-specific ML models, legacy retrieval, and incident workflows.
version: 0.1.0
---

# InfraGuard AI — Agent Implementation Skill

> **Instructions for coding agents and teammates.** Read `README.md` first. This file is a build specification, not evidence that datasets were downloaded, models trained, or performance achieved. Implement only what is supported by the data. Never claim an unverified result.

## Mission

Create an explainable multi-model infrastructure intelligence stack with a **Python 3.11+ FastAPI/Pydantic v2 backend** and a **React + TypeScript + Vite frontend**. FastAPI serves all data, inference, incident, and legacy operations; React only consumes the versioned API. **Do not concatenate UCI AI4I, Backblaze, C-MAPSS and ASHRAE into one universal classifier.** Each domain has different units, targets, sampling protocols, hazards and notions of failure. Normalize their *outputs* and provenance through a shared API while retaining domain-specific models and valid domain-specific evaluation.

### Completion order

1. Repo scaffolding with `backend/` FastAPI app, `frontend/` React/Vite app, environment setup, cross-origin configuration, and contract tests.
2. `industrial_failure_v1` with AI4I as a fast, **synthetic industrial classification baseline**.
3. `facility_anomaly_v1` as a **transparent synthetic scenario** for dashboard integration.
4. `drive_failure_v1` with real Backblaze snapshots and rigorous future-window labels if compute/time permits.
5. FastAPI routes + React dashboard, legacy CSV parsing/retrieval, impact/handoff service and tested full-stack demo.
6. Optional NASA RUL and ASHRAE energy anomaly models *only after primary demo works*.

If a dataset is unavailable, licensed restrictively, too large, or missing required identifiers/labels, **stop that subtask, document the blocker, and continue with the viable modules**. Do not generate fake evaluation statistics.

## Agent operating rules

- First inspect repository tree and existing files. Reuse existing conventions. Do not overwrite human work.
- Propose a short implementation plan in the PR description; implement in small testable commits.
- Cite the precise external dataset URL, publication/snapshot version, downloaded file list, date ranges, applicable terms and any SHA-256 hashes in `docs/datasets.md`.
- Keep raw downloads, generated large data, secrets and large model binaries out of Git. Put paths in `.gitignore` and add small fixtures for tests.
- Pin packages in `pyproject.toml` or `requirements.txt`; document Python version and reproducibility seed. Make all paths configurable, not hard-coded to teammates' machines.
- Never represent a source domain model as validated for other domains. Example: AI4I cannot be renamed `cooling_failure_model`.
- Prefer deterministic, explainable baselines before advanced algorithms. Compare against naive/majority or rule-based performance.
- Separate training, validation, and final test. Select features/thresholds/hyperparameters on training/validation **only**, then evaluate once on held-out test.
- Never leak future data into any feature, score, imputation, scaler, rolling window or target construction.
- All outputs include `model_id`, model version, outcome definition, time horizon (if any), input timestamp, score interpretation, provenance, and limitations.
- Do not attempt to control live power, cooling, industrial machinery or data-center equipment. Propose only human-reviewed steps.
- For datasets with tiny/rare failure classes, include the event count in each split and flag inadequate test samples.

## Phase A — Repo and reproducibility scaffold

Implement this target layout if missing, adapting to existing project code without destructive rewrites:

```text
README.md
SKILL.md
backend/
  pyproject.toml
  .env.example
  app/
    main.py
    core/{config.py,errors.py,logging.py}
    api/v1/{router.py,health.py,assets.py,models.py,predictions.py,scenarios.py,legacy.py,impact.py,incidents.py}
    schemas/{assets.py,predictions.py,scenarios.py,legacy.py,incidents.py,errors.py}
    services/{prediction_service.py,simulation_service.py,legacy_service.py,impact_service.py,incident_service.py}
    db/{base.py,models.py,session.py}
  alembic/
  tests/{test_health.py,test_predictions_api.py,test_scenario_api.py,test_incidents_api.py}
frontend/
  package.json
  tsconfig.json
  vite.config.ts
  .env.example
  src/
    main.tsx
    App.tsx
    api/{client.ts,types.ts}
    components/{Layout.tsx,StatusBadge.tsx,TelemetryChart.tsx}
    pages/{Overview.tsx,Assets.tsx,AssetDetail.tsx,Simulation.tsx,Incidents.tsx,IncidentDetail.tsx,Models.tsx}
    hooks/
    features/
  tests/
configs/{models.yaml,scenarios.yaml}
src/infraguard/
  ingest/{ai4i.py,backblaze.py,cmapss.py,ashrae.py}
  features/{industrial.py,drive.py,facility.py}
  models/{train.py,evaluate.py,predict.py,registry.py}
  simulation/{generator.py,scenarios.py}
  legacy/{parser.py,retriever.py}
  impact/calculator.py
scripts/{prepare_ai4i.py,train_industrial.py,prepare_backblaze.py,train_drive.py,run_demo.py}
tests/{test_ai4i_leakage.py,test_drive_labels.py,test_splits.py,test_inference_schema.py,test_facility_scenarios.py}
artifacts/{metrics,model_cards}/
docs/datasets.md
```

Commands below are **target commands to implement**, not claims they currently work:

```bash
# From repository root: train models in the Python project environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e ./backend
pip install -e .               # if root pyproject packages src/infraguard
python scripts/prepare_ai4i.py
python scripts/train_industrial.py
pytest -q

# Terminal 1: Backend
cd backend
uvicorn app.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend
npm install
npm run dev
npm run build
```

Ensure install order and editable-install paths match the actual `pyproject.toml` layout. If the shared `src/infraguard` is a separate Python package, declare it as a proper dependency or install from the repo root; do not rely on accidental `PYTHONPATH` paths. Train scripts must accept `--config`, `--data-path`, `--output-dir`, and optionally `--seed` or equivalent CLI arguments; provide `--help`.

Write `configs/models.yaml` with domain-specific configs: outcome, horizon, lookback, features, split method, seed, candidate algorithms, metric thresholds, source path, and missing-data policy. Don't assign unsupported default performance guarantees.

## Phase A2 — Mandatory FastAPI implementation instructions

1. Implement FastAPI **app factory / app object** at `backend/app/main.py`; use a `/api/v1` `APIRouter`, request and response Pydantic models, dependency-injected database sessions, structured logs, versioned OpenAPI and explicit CORS origins. Prefer synchronous endpoints for CPU-bound inference; don't block the event loop with model training or bulk files.
2. Add endpoints listed in README Section 9: `GET /health`, `GET /assets`, `GET /assets/{id}/telemetry`, `GET /models`, `POST /predictions`, `POST /scenarios/{id}/start`, `GET /scenarios/{run_id}/events`, `POST /legacy/import`, `GET /assets/{id}/maintenance`, `POST /impact/estimate`, `GET/POST /incidents`, `POST /incidents/{id}/approve`, and `GET /incidents/{id}/handoff` (all under `/api/v1`).
3. Keep HTTP endpoints thin: parse and validate → call typed service → serialize response. ML model adapters live outside routes. Load versioned pipelines with fixed feature order at startup/on-demand, and return `model_unavailable` if no trained artifacts exist. Never retrain on incoming HTTP requests.
4. Store asset, telemetry, work order, incident and approval records with SQLAlchemy/SQLite for MVP and Alembic migrations. Maintain original legacy raw text and source-file/row references. Make DB and model path configurable via environment variables.
5. Predict **only** for compatible asset types and exact model feature contracts. Return `{score,score_type,target,horizon_days,model_id,model_version,observed_at,source_dataset,is_synthetic,limitations,evidence}`. If no valid model exists, use `status=insufficient_data` with `score=null` rather than making up a number. Never conflate a risk label and failure probability.
6. `POST /scenarios/{id}/start` creates a deterministic replay run; `GET /scenarios/{run_id}/events?after=<cursor>` lets UI poll reproducibly. Include stable event ID, UTC timestamp, metric units, `is_synthetic=true`, and scenario ID. WebSocket/SSE optional *after* polling works.
7. Validate upload extensions, MIME/size and CSV schema; secure storage names and reject malformed inputs with clear, non-sensitive 4xx errors. Enforce allowed incident status transitions on server, and write an audit record when an operator approves a **demo** action. No live building controls.
8. Use standard JSON error envelope `{ "error": { "code": "string", "message": "string", "details": {} } }`. Include 404 missing asset, 409 invalid transition, 413 oversized upload, 422 bad schema and 503 unavailable model tests.
9. Use FastAPI `TestClient`/`httpx` and dependency overrides for deterministic fixtures. Tests must hit real routes and validate response schemas, errors, model routing, and synthetic provenance. Avoid silently mocking all business logic.

## Phase A3 — Mandatory React + TypeScript implementation instructions

1. Scaffold **React + Vite + TypeScript** in `frontend/`. Use React Router for `/`, `/assets`, `/assets/:id`, `/simulate`, `/incidents`, `/incidents/:id`, `/models`.
2. **All data comes through FastAPI**, via a typed `frontend/src/api/client.ts`. Prefer generating TypeScript types from FastAPI OpenAPI; otherwise maintain schema-alignment tests. Use TanStack Query for fetching, loading/error/empty states, pagination and re-fetching. Do not implement a second Node/Express API or put Python model logic in JS.
3. Implement reusable charts (Recharts), assets/alerts table, incident timeline, evidence panel showing exact maintenance source, editable impact assumptions, model-info panel, and explicit synthetic/real/prototype status indicators. Include units, timestamps, outcome definitions, score type, limitations and missing-data notices.
4. The scenario page must start and reset a simulated replay, poll events and update charts; avoid a purely animated front end disconnected from API state. The incident page must call real FastAPI endpoints for opening an incident and proposing/approving a demo action, and show server-reported changes.
5. `VITE_API_BASE_URL` is the only browser API base configuration. **Never expose LLM tokens, database credentials or model secrets through `VITE_*`.** Backend `FRONTEND_ORIGINS` includes only local Vite URL during development; production origins must be explicit.
6. Ensure keyboard navigation, text labels (not just red/green), usable error notices and a loading spinner/skeleton. Add Vitest/React Testing Library (or equivalent) for key components and one browser E2E check (Playwright optional) for scenario → incident → handoff.
7. `npm run build` and TypeScript check must succeed; no hard-coded fake model scores when backend responds with unavailable. The React UI should say *not evaluated* when metrics are absent.

### Backend/frontend integration acceptance test

From a clean repo checkout: install backend and frontend; start FastAPI on port 8000 and Vite on 5173; visit Overview; load assets; start a synthetic cooling anomaly; observe event chart and evidence; create an incident; retrieve a legacy source note; calculate impact with visible assumptions; approve a **demo** handoff; open model transparency page and inspect a real model card. All values must be obtained from the backend or explicitly identified static demo fixtures. API `/docs` must match requests used by the client.

## Phase B — Common data governance and quality checks

**Create a dataset manifest** per source: publisher, URL, version/period, units, schema, number of rows/assets/events, class balance, duplication strategy, license, assumptions, and caveats.

Required validations:

1. Unique logical key (dataset-specific); detect duplicates and conflicts before deduplication.
2. Consistent timestamp timezone, units and monotonic ordering per asset; document conversions.
3. Missing value % by feature, missingness patterns by device model/time, cardinality of identifiers.
4. Failure/event prevalence and counts per split (including no-event or censored records).
5. No target/cause label, target proxy, row IDs, or future observation in features.
6. Train/test separation checked by code and reported in metrics JSON.
7. No global preprocessing fit on all rows: use scikit-learn `Pipeline` / `ColumnTransformer` fit on training data only.
8. Explicit out-of-distribution detection (unknown equipment category/model, missing key fields, out-of-range sensors) with abstention or warning.

Prefer Parquet for model-ready intermediates, small CSV fixtures for review. All synthetic records must have `is_synthetic=true` or equivalent provenance.

## Phase C — Model 1: AI4I synthetic industrial failures (`industrial_failure_v1`)

**Purpose:** demonstrate a complete classification workflow quickly. **Not** a real cooling-unit or data-center model.

**Source:** UCI AI4I (https://archive.ics.uci.edu/dataset/601/ai4i), 10,000 synthetic records; license CC BY 4.0. Use official download or `ucimlrepo.fetch_ucirepo(id=601)` with source attribution.

**Target:** `Machine failure` — failure at the example's observation, **not** failure in the next 24 hours. Do not invent a forecast horizon.

**Possible safe inputs:** `Type`, `Air temperature [K]`, `Process temperature [K]`, `Rotational speed [rpm]`, `Torque [Nm]`, `Tool wear [min]` (verify actual column names on load).

**Exclude from inputs:** `Machine failure`, `TWF`, `HDF`, `PWF`, `OSF`, `RNF` (target and failure-mode labels), `UDI`, `Product ID`, near-unique IDs and any labels derived from outcome. If a field is present under another name, exclude by semantic role rather than string alone.

**Split strategy:** stratified train/validation/test split with fixed seed as a benchmark; explicitly note the limits of random splitting on a synthetic cross-sectional benchmark. Check for product/type imbalance. Use distinct partitions; do not fit transformations on validation/test data.

**Implement:**

1. Load and schema-check.
2. Explore target balance and failure cases; log counts.
3. Baseline `DummyClassifier` and regularized logistic regression with a preprocessing pipeline (one-hot encode categorical `Type`, impute/scale numeric as needed).
4. Train Random Forest or gradient boosting as a stronger candidate; use modest hyperparameter search on training/validation only.
5. Report per-class precision/recall/F1, confusion matrix, PR-AUC (`average_precision_score`), ROC-AUC (if valid), calibration curve/Brier score if probabilities will be displayed.
6. Tune an operating threshold according to documented costs for false negatives vs false positives; show threshold and validation-selection method.
7. Evaluate final frozen candidate on test **once**, preserve model + pipeline, feature schema, split indices and metrics JSON.
8. Save `artifacts/model_cards/industrial_failure_v1.md` with domain restriction: "synthetic manufacturing-machine benchmark; not validated for facility operations."

**Acceptance tests:** no failure-mode targets in X; inference returns same schema on one row; train-only fit; reproducible split; tiny fixture passes through all stages; false-positive/false-negative cases visible.

## Phase D — Model 2: Backblaze drive failure (`drive_failure_v1`)

**Purpose:** estimate observed **drive** failure risk within a stated future window from daily snapshots. This is the closest source to real data-center hardware.

**Source:** https://www.backblaze.com/cloud-storage/resources/hard-drive-test-data. Backblaze publishes daily S.M.A.R.T. snapshots and failure indicators; field availability and definitions change by quarter/model. Record exact quarters, storage formats, schema snapshots and access dates. Choose a limited documented cohort rather than downloading every year at once.

### D1. Cohort and target definition

Choose a horizon `H` (e.g., **30 days**) and a retrospective lookback `L` (e.g., 7 or 30 days) in configuration. These are suggested design choices, **not** dataset-provided defaults.

For a snapshot from drive `d` on date `t`, the label is `1` **only if an observed qualifying failure** occurs for `d` within `(t, t+H]`. Avoid treating a failure-day snapshot or any post-failure record as a prediction input.

**Critical censoring:** a drive that disappears from the data is not automatically a failed drive, and a row near the end of downloaded coverage is **not** a negative merely because no subsequent failure is visible. Exclude, censor, or handle such rows with a justified survival-analysis approach. Document whether removed/replaced drives without failure are right-censored. Do not assume a drive's every missing day is a failure.

If treating failure-day observations as events, inspect publisher definitions and exclude variables populated only when the failure is already identified.

### D2. Feature engineering

Use fields **available at or before t**, such as:

- Drive model, capacity, age proxy if reliably observed, site context only if available and appropriate.
- Available S.M.A.R.T. raw/normalized attributes (e.g., reallocated sectors, pending sectors, uncorrectable errors, power-on hours) after checking semantics and missingness **per model**.
- Lagged changes, counts, rolling medians/trends over `L` using only historical snapshots: `shift(1)`, `rolling(..., closed='left')` where applicable, and careful indexing.
- Missingness indicators for attributes not supported by a given hardware model.

S.M.A.R.T. attributes are not uniformly comparable across manufacturers; compare model-specific pipelines or include device-model-aware preprocessing. Do not interpret any attribute as a universal temperature or failure signal. Drop serial numbers from model features but retain them for grouping and joining.

### D3. Split and evaluation

- Prefer **chronological holdout**: earlier periods for train, later period for validation, latest untouched period for test; embargo a gap of at least `H` at boundaries so horizon labels do not cross training/evaluation partitions. Carefully define how label observation windows work at boundaries.
- Optionally conduct separate **held-out-drive/model** generalization studies. If identities appear across chronological partitions, call this a future-time test, not an unseen-drive test; conduct grouped tests to examine identity leakage.
- Avoid thousands of highly correlated daily rows inflating metrics. Consider periodic index dates and event-aware metrics with clear sampling/weighting. If using downsampling, evaluate on a naturally prevalent holdout; correct probability calibration if prevalence shifts.
- Measure **PR-AUC**, precision/recall at an operational alert budget, false alerts per 1,000 drive-days, events detected with lead time, event-level recall, and Brier/calibration on a time-based test. Report total failures, unique drives, coverage, horizons, and confidence intervals where feasible.
- Baselines: prevalence-only, simple SMART alert heuristic, logistic regression; then gradient boosting/XGBoost or Random Forest when justified.
- Use an explicit decision threshold and an `insufficient_data` status if essential fields are missing.

**Do not promise a validated 87% failure probability** unless calibration and evaluation establish it. Most failures are rare, and a seemingly high accuracy can be meaningless.

### D4. Artifact and tests

Deliver `prepare_backblaze.py`, `train_drive.py`, a source manifest, reproducible cohort manifest, train/val/test ranges, feature spec, evaluation plots, metric JSON and `drive_failure_v1.md` model card.

Required unit tests:

- A failure occurs 5 days after index → positive when H ≥ 5.
- A failure occurs 31 days after index → negative for H = 30 **only if full 30-day follow-up exists**.
- Observation at right edge with incomplete H → censored, **not negative**.
- Silent drive disappearance → censored/unknown, **not failure**.
- No row at/after failure may contribute training inputs for pre-failure risk.
- Grouping and rolling windows never incorporate readings after index time.
- Validation/test future labels never become training features.

## Phase E — Model 3: Facility anomaly (`facility_anomaly_v1`)

**Purpose:** provide a compelling, safe, reproducible data-center cooling/UPS demonstration while being honest that public datasets above do not directly label cooling-unit failures.

Generate synthetic measurements for `CRAC`, room inlet/outlet temperatures, fan status, UPS voltage/load, equipment utilization, and optional environmental conditions. Use plausible engineering units, **document synthetic rules as assumptions** rather than claiming universal safety thresholds.

Scenarios:

- Normal operation with noise and load variation.
- Gradual rising temperature (degraded cooling efficiency).
- Short isolated sensor spike (should avoid excessive false alerting).
- Sensor dropout/missingness (report degraded observability rather than fake normal).
- UPS load increase or simulated capacity reduction.

**Initial detection:** simple thresholds + rolling trend or residuals, with minimum-persistence conditions and clear textual rationale. Optionally compare isolation forest or forecasting residuals; train only on representative **normal synthetic** behavior, evaluate on **held-out synthetic scenarios**. If anomaly labels are produced by the same handcrafted rules, do not present the model's agreement with those labels as proof of field accuracy.

Output `score_type='heuristic_anomaly_score'` (not calibrated failure probability), `is_synthetic=true`, triggered rule/metric, observed timestamp, and recommended human inspection. Never automatically change production settings.

Tests: known anomaly triggers; brief noise spike shouldn't always trigger; missing data raises `insufficient_data`; no future values used; reproducible scenario seeds.

## Phase F — Optional model 4: NASA C-MAPSS RUL (`engine_rul_research_v1`)

**Purpose:** show ability to predict degradation trajectories on **simulated aircraft engines**, NOT actual data-center equipment.

Use NASA PCoE turbofan degradation simulation dataset via https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/ (verify dataset download and redistribution). Use published train/test unit partitions where provided.

- Target: remaining cycles for a particular engine observation, based on **known run-to-failure training sequences** and benchmark test labels where available.
- Features: operating settings, sensor channels and **past-only** lag/rolling trends; never use end-of-life cycle or maximum cycle as an input feature.
- Split by engine unit or prescribed benchmark split. Never randomly split rows from the same run across train/test.
- Baselines: simple mean/linear regression; compare gradient-boosted trees, optional sequence models only if justified.
- Report MAE, RMSE and error by early/late degradation stage; show units (`cycles`) and negative/implausible prediction handling.
- Place behind a **research** tab until there is relevant domain transfer evidence.

## Phase G — Optional model 5: ASHRAE building energy anomalies (`building_energy_anomaly_v1`)

**Purpose:** forecast expected meter readings and flag deviations, NOT claim labeled physical breakdowns.

Source: https://www.kaggle.com/competitions/ashrae-energy-prediction/data. Respect competition access and data restrictions.

- Join readings, building metadata and weather **only on appropriate building/site/time keys**; handle timezone and gaps.
- Target: energy demand or residual anomaly against a weather/seasonality baseline; no fabricated failure labels.
- Split chronologically and group/stratify by building for generalization tests where relevant.
- Baselines: historical same-hour/day or seasonal average; compare gradient boosting after robust feature engineering.
- Metrics: MAE/RMSE and residual coverage, evaluated on held-out periods. Anomaly precision/recall **cannot** be calculated without trustworthy anomaly ground truth.
- Output `score_type='energy_residual_anomaly'`; don't confuse it with failure probability.

## Phase H — Output normalization, priority logic and orchestrator

A **shared data platform does not imply a shared model**. Build a type-safe prediction adapter:

```python
class PredictionResult:  # pseudocode; implement as Pydantic model
    asset_id: str
    model_id: str
    model_version: str
    observed_at: str
    generated_at: str
    target: str
    horizon_days: int | None
    score: float | None
    score_type: str             # calibrated_probability | raw_model_score | heuristic_anomaly_score | rul_cycles | energy_residual_anomaly
    threshold: float | None
    risk_label: str             # normal | review | critical | insufficient_data
    source_dataset: str
    is_synthetic: bool
    evidence: list[str]
    limitations: list[str]
```

Implement **routing** by asset type and feature contract:

- `storage_drive` → Backblaze-trained drive model only when inputs satisfy schema; otherwise abstain.
- `industrial_machine` → AI4I-trained model **only for appropriate benchmark/demo measurements**.
- `cooling_unit`, `ups`, facility sensors → facility anomaly/rules until domain-validated models exist.
- `aircraft_engine_research` → C-MAPSS RUL module, separate from operational site views.
- `building_meter` → ASHRAE energy residual detector; **not** a verified failure indicator.

An orchestration/policy module may rank alerts based on severity, impact exposure, asset criticality and data reliability, with explicit policy thresholds. **Never numerically average unrelated model scores or translate an anomaly score into a failure probability without calibration.**

## Phase I — Legacy record intelligence and impact (sponsor integration)

### Legacy parser and retrieval

- Accept documented CSV and simple text exports with column maps (`legacy_id`, `timestamp`, `note`, `work_order_status`, `site`).
- Normalize IDs with deterministic mapping; send ambiguous matches to human review.
- Retain `source_file`, `source_row`, `raw_text` and original timestamps.
- Index by asset and keyword/embedding similarity. Search must filter or re-rank by **correct asset identity** and dates, not return a different site's incident because text looks similar.
- LLM extracts structured observations, then summarizes **only retrieved records** with references; mark unverified interpretations and never fabricate a maintenance event.
- Evaluate retrieval on a tiny curated fixture (e.g., known asset matching, distractor with similar symptoms, outdated note). Report hit@k and unsupported-claim rate from review.

### Business impact estimator

Use a small dependency graph in a scenario fixture: cooling unit → room → rack(s) → service(s). For example:

```
expected_scenario_loss = duration_hours * affected_service_cost_per_hour + direct_repair_cost
```

Only apply that formula to mutually non-overlapping exposure; show editable values and distinguish **scenario estimate** from realized loss, contract SLA penalties, or measured savings. If inputs are unavailable, return a range or `unknown` rather than making up figures.

### Incident workflow

`detected → investigating → action_proposed → human_approved → resolved`.

Keep evidence trails and change logs. No autonomous shutdowns, control-panel writes, or network interventions. Manual human approval required for tickets or operational changes (even when mock APIs are used).

## Phase J — Evaluation standards and release gate

**For every trained model create:**

- `artifacts/metrics/<model_id>.json`: exact splits, dates, group counts, positive counts, baseline, candidate results, chosen threshold, held-out metrics, calibration status and run seed.
- `artifacts/model_cards/<model_id>.md`: intended use, prohibited uses, source/license, target, horizon, data coverage, performance by important subgroups/model families, error examples, uncertainty, drift concerns and limitations.
- Plots: confusion matrix and PR curve for classifiers; calibration plot if output called a probability; residuals/RUL error for regressors.
- One reproducible command and an inference smoke test for a small fixture.

### Accuracy cannot be a single number

For rare failures: prioritize PR-AUC, false-alert rate, event recall and actionable lead time. Report precision/recall trade-offs at a **fixed operational alert budget**. Calibrate probabilities on held-out validation data, then assess calibration on test; never call a raw Random Forest/XGBoost output an assured real-world risk probability without evidence.

**Deployment acceptance:**

- Pass schema and leakage unit tests.
- Beat the appropriate naive baseline **on held-out data** for the chosen task or report that the model does not.
- No unsupported generalization from manufacturing/aircraft datasets to HVAC or UPS.
- Persist versioned preprocessing + model + feature list and refuse malformed input.
- Dashboard identifies source, timestamp, score type and `synthetic` status.
- Human approval and evidence/source trace available for every actionable incident.

If a metric cannot be reliably calculated, write **"not evaluated"**. A failed or weak evaluation is a valid research result, never a reason to invent success.

## Phase K — Tests the agent MUST write

1. **Split integrity:** no forbidden train/test ID overlap for grouped experiments; time boundaries correct; no horizon leakage.
2. **Feature leakage:** target/cause indicator never present; future-derived columns and identifiers blocked.
3. **Backblaze censoring:** incomplete 30-day follow-up and silent disappearance are not falsely negative/failure.
4. **Time-series joins:** weather/telemetry joins never pull future readings.
5. **Unit/schema validation:** Kelvin vs Celsius, missing SMART attributes, unexpected string values, unknown model IDs.
6. **Inference:** known fixture loads exact training pipeline and matches schema/order.
7. **FastAPI:** wrong asset type/model returns `unsupported` or `insufficient_data`, not a bogus score; 404/409/422/503 cases and schema contracts checked.
8. **Scenario:** reproducible normal and failing sequences; spike and sensor dropout conditions.
9. **Legacy:** correct asset match, duplicate ID, ambiguous mapping, conflicting record and unsupported summary assertion.
10. **Impact:** zero duration, unknown rate, shared dependencies (no double count), transparent assumption display.
11. **Security/safety:** no secrets in output, no production controls, human-approved incident transition.
12. **React/frontend:** typed client matches OpenAPI, loading/error/empty states, synthetic and score-type badges, model-unavailable UI, integration replay works.
13. **Full-stack smoke:** Vite-to-FastAPI CORS/proxy works; a single synthetic incident round trip persists and is reflected in dashboard; frontend build and TypeScript check pass.

## Deliverables and agent handoff report

Before closing the task, provide teammate(s) a **single concise handoff** containing:

1. Files created/changed and purpose.
2. Exact dataset URLs/snapshot slices acquired; any license/access/size blockers.
3. Reproducible setup, train, evaluate and demo commands that were **actually tested**.
4. Per-model target/horizon/features/splits; metric JSON and model-card paths; limitations.
5. Test results and any failing tests; no invented metrics.
6. How demo reports synthetic vs real measurements.
7. Known issues, next prioritized actions, and a minimal working incident walk-through.

### Suggested prompt for implementing agent

> Read `README.md` and `SKILL.md` completely. Build **Python FastAPI + Pydantic v2 backend** and **React + TypeScript + Vite frontend**, connected through tested `/api/v1` JSON contracts. Scaffold testable data models; implement leakage-safe AI4I training and deterministic facility anomaly simulation; add a Backblaze future-horizon drive model if feasible. Never merge unrelated datasets into one model. Add real API-driven dashboard, asset details, incident/legacy/impact views, and a synthetic scenario replay. Persist versioned model metadata and actual evaluation artifacts. Require human approval for actions. If a dataset is too large or missing, document the blocker rather than claiming success. Verify backend tests, frontend build, and one end-to-end incident demo.

## Source list

- HackUTD slides supplied in this conversation: NMC² p.6, CBRE p.12, 8090.AI p.4.
- UCI AI4I: https://archive.ics.uci.edu/dataset/601/ai4i
- Backblaze Drive Stats: https://www.backblaze.com/cloud-storage/resources/hard-drive-test-data
- NASA PCoE: https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/
- ASHRAE: https://www.kaggle.com/competitions/ashrae-energy-prediction/data
