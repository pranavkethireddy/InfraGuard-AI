# InfraGuard AI — frontend

Vite + React + TypeScript SPA (React Router, TanStack Query, Tailwind v4, Recharts, Vitest).
Frontend only: no backend, auth, database or ML in this folder.

## Setup

```bash
npm --prefix frontend install
cp frontend/.env.example frontend/.env   # optional
npm --prefix frontend run dev            # http://localhost:5173
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build          # output: frontend/dist
```

## Data modes

| `VITE_DATA_MODE` | Behaviour |
| --- | --- |
| `fixture` (explicit offline preview/tests) | Serves the approved contract fixtures in `src/api/fixtures/contracts/` verbatim through the same typed client (404 for anything without a fixture). A persistent "Fixture preview — illustrative data, not live" banner is shown. All mutations are disabled. Fleet snapshots are static; the approved mining status fixture is available, but no mining map/rack fixture exists. |
| `live` (default) | Calls `VITE_API_BASE_URL` (default `/api/v1` on the origin where the app is opened). Errors (`{error:{code,message,details,request_id}}`, HTTP 404/409/422/503 or network) are shown with the request ID. **There is never a fallback to fixtures.** |

Vite preserves the `/api` prefix and proxies requests and EventSource streams to `http://127.0.0.1:8000`: `/api/v1/ops/stream` remains `/api/v1/ops/stream` upstream. The browser uses the frontend origin, including when opened by LAN IP. Start the existing backend separately; no backend configuration is changed by this export. An explicit absolute `VITE_API_BASE_URL` (e.g. `https://api.example.org/api/v1`) works for both fetch and streams; that API must already permit your frontend origin. The Vite proxy is development-only: deployed hosting needs an existing same-origin `/api` reverse proxy or an explicitly configured reachable absolute API URL.
`VITE_*` values are bundled into the browser — never put secrets in them.

## Fixtures

`src/api/fixtures/contracts/*.json` are exact approved copies of `contracts/fixtures/`; GPU PR47 and floor/pager PR49 are merged on public main. Pager claim/walking/action and stream examples are test-only; the fixture pager displays a clearly labelled static paged snapshot, never a fake executed action.
`src/api/fixtures/index.ts` checks them against the TypeScript contracts at compile time; `src/test/fixtures.test.ts` checks enum values at runtime.
`model.evaluated.example.json` is used only in tests and is never displayed as a measured result.

## Tooling

- `package-lock.json` is committed; use `npm ci` in CI.
- Vitest 4.1.12+ (no tinypool dependency; `npm audit` reported 0 vulnerabilities at export time).

## Routes

`/?site=datacenter|mining`, `/fleet?site=datacenter|mining`, `/assets`, `/assets/:id`, `/simulate`, `/incidents`, `/incidents/:id`, `/models`.

`/operations?site=datacenter|mining` provides the backend-ranked repair plan, fictional demo crew, read-only shared learning matrix and site/asset-type-filtered cases. Incident detail adds `/incidents/{id}/whatif` with returned option costs, curves, power states and recommendations. Null values or absent curves mean unavailable, not zero/no risk. All durations are DEMO time, not wall-clock repair promises.

Operations plan, what-if and learning queries refresh every second while their page is open. Overview/Operations crew use an initial GET and `event: crew` from `GET /ops/stream?site=` instead of continuous crew polling. Incident repair status/current site work orders retain 1-second lifecycle polling until backend resolution. Dispatch is an explicit POST `{incident_id,option}` (plus `technician_id` only when explicitly selected), never triggered on mount. Pending/fixture/resolved/already-dispatched actions (including paged and awaiting_confirmation orders) are blocked. Errors preserve evidence and request IDs; no automatic retries of mutations. Completion costs use current work orders, not the labelled initial dispatch snapshot. Resolution refreshes learning.

## Floor, pager and tablet setup

Overview combines `GET /ops/floor?site=` with hall-local fleet coordinates translated once by the returned hall origin. Doors, corridor, technician positions and paths are already site-global. Positions/paths and walking DEMO minutes are backend values; no closest-technician, travel-time or movement calculation runs in the browser. Missing coordinates retain a technician text list. Site changes close streams and clear selections.

`/pager?technician=tech-03` defaults to Sam Rivera; select another returned technician via the floor link or technician ID field. Initial `GET /ops/pager/{encodedId}` and `event: pager` from `/ops/stream?technician_id=` share the configured `VITE_API_BASE_URL` (including `/api/v1`). Monotonic versions protect against older GET/POST/SSE responses. Stream state reports connecting/live/reconnecting/error/stale while retaining last good data; fixture mode opens no EventSource. Claim/release are explicit bodyless POSTs only, never automatic on mount/unmount. Actions POST `{action,work_order_id}` and render only returned accept/decline/done permissions; no Arrived endpoint. Pending requests block duplicates. 409 NOT_YOUR_JOB/NOT_PAGED/NOT_STARTED refetch authoritative state for manual review/retry. Device-controlled is demo backend state, not security identity. Operations has an explicit automatic-dispatch switch; Overview only displays the returned state.

For a local iPad, use the same trusted Wi-Fi as the laptop, or use an already deployed public URL. A proxy alone does **not** make a laptop reachable across separate networks. No tunnel, deployment, router port forwarding or backend CORS/env changes are performed here.

1. Run your existing FastAPI backend locally at `127.0.0.1:8000`; it need not be LAN-exposed for the Vite proxy.
2. Keep `VITE_API_BASE_URL=/api/v1` and `VITE_DATA_MODE=live` (the defaults).
3. When you choose to start development, `npm --prefix frontend run dev` has LAN host support (`0.0.0.0`). Open `http://LAN_IP:5173/pager?technician=tech-03` on the same-Wi-Fi iPad, using the laptop address. Local firewall/network restrictions may still prevent access. Restrict access to your trusted network; this is not deployment or authentication.

Pager controls have 44px+ touch targets, keyboard focus, and locally scrolling tables for portrait/landscape. Community impact #44 is not implemented because its contract is not approved.

`/servers/:id?gpu=returnedIndex` drills from returned rack `server_ids` to the actual server/GPU index. `GET /fleet/servers/{encodedId}?history=30` polls every second with a distinct server query key. GPUs, online/power state, PSU redundancy, ECC, cooling, incident links and job reasons/prices are returned values only. GPU histories use only provided per-GPU fields; nulls are Not reported. Overview/Fleet jobs come from `FleetMap.jobs` (the jobs fixture is an excerpt, not a separate endpoint). GPU rule scores are heuristic, not probabilities. Fleet controls offer a returned GPU-server inventory picker; server drilldown targets its returned server ID. Explicit fault choices send `{asset_ids:[actualSelectedServerId],kind:"gpu_fault"}` (GPU fails) or `kind:"server_crash"` (Whole server down). Loading, empty, failed, fixture and pending states block mutations; 422 FAULT_KIND_NOT_SUPPORTED shows the request ID. Pending backend deployment can return 404/503 with a request ID; no live fallback. GPU-hour prices are demo assumptions, not bills.

## Contract rules

- Overview opens on the data center floor map; URL site selection, rack details, summary, affected machines and incidents use the same site-isolated 1-second fleet queries. The functional Start loop / inject faults link opens full controls on `/fleet` for the selected site. No automatic mutations.
- Health and power are separate: optional backend `on`/`at_risk`/`off` power states, reasons, shutdown ETA and current work orders are displayed without inference. Missing old-fixture fields say Not reported; no readings never means all good. OFF uses dark markers with red outlines/text; at-risk uses amber. Shutdown/technician ETA is labelled DEMO minutes, progress is the returned fraction. Power test examples are test-only; approved production fixtures remain unchanged.
- Injected faults hold until technician repair or operator incident resolution; the frontend does not promise automatic fault recovery. Operations controls live on `/operations` and incident detail, never Overview.
- Fleet sites share one backend live loop. Site tabs persist in `?site=`; switching clears rack selection and action feedback. Map/status/rack query keys include site and poll every 1 second with `history=30`. Site directory metrics also refresh every second. Backend machine ordering is preserved.
- Floor-grid coordinates and hall dimensions are returned by the backend; racks support click, Enter and Space, with status labels and a legend. Rack detail renders returned reasons, cooling relationships, machines, incident links and each `chart_fields` history.
- Start posts `{seed:42,tick_seconds:1}`; stop preserves data; faults post `{count:3,site:selectedSite}` and may start the shared loop. Nothing auto-starts on mount. Clear requires confirmation: all readings/predictions/incidents across BOTH sites are deleted, faults cleared and single-asset simulations reset, while the live loop continues.
- Queued/running incident investigations poll every second; optional problem/likely cause and business fields are displayed only when returned. Hashprice source/date comes from the API, distinct from demo repair/downtime assumptions. Heuristic mining scores and uncalibrated drive scores are not probabilities; a returned 720h drive horizon is shown as 30 days.
- Assets use real `limit=50&offset=` pagination driven by returned total (including the new 262-asset fleet). Simulator compatible-assets discovery requests all pages at `limit=200&offset=` before offering any options; failures never expose a partial list. No fixture fallback on live failure.
- The hosted Lovable preview remains fixture by default. This standalone export remains live by default; Vitest explicitly sets fixture mode unless a test mocks live HTTP. No Gemini or other private key belongs in `VITE_*`.

- All risk levels, scores, costs, impact and priority values are displayed exactly as the API returns them; the browser never computes them.
- Compact Estimate indicators open source/provenance details: repair/GPU prices are demo assumptions, never actual billing. Historical mining hashprice source/date stays inspectable separately from repair assumptions. Job pace, lost USD/hour and site GPU money remain directly visible. Synthetic data and score types remain labelled; the fixture banner is always prominent.
- `heuristic` and `model_score` values are labelled "not a probability"; only `calibrated_probability` is called a probability.
- Models without returned metrics show "Not evaluated" (or "not applicable" for rules). No metrics are invented.
- Impact assumptions are read-only (editing deferred). There is no approve/handoff action.
- Simulations: `POST /simulations`; recovery via `GET /simulations?asset_id=` (backend ordering) picks a running run, otherwise the newest completed run; reset runs are never shown as active. A completed run keeps its status, readings and Reset across route changes and reload until reset succeeds. Status and `GET /assets/{id}/readings` are polled every 2 s while running. `POST /simulations/{id}/reset` clears the selection and cache and refreshes assets/readings/incidents. Seed must be a whole number ≥ 0. Start is disabled while recovery loads. A 409 shows "already running".

## Layout

```
src/api/        typed client (client.ts), contracts (types.ts), queries (queries.ts), fixtures/*.json
src/components/ shell, badges, charts, model card
src/lib/router-adapter.tsx  router-neutral link used by pages
src/pages/      one component per route
src/App.tsx     react-router-dom routes
```

### PR60 live priority

Simulate and Models are absent only from sidebar navigation; `/simulate` and `/models` remain functional. Incident rank is returned `priority_rank` (1 fix first, 5 can wait), not a conversion from index/risk. Plan, task and pager rows fetch referenced incident IDs directly, sharing per-ID query caches with one-second unresolved refresh; absent ranks show Not reported and failed lookups show errors/request IDs. Technician queues follow `queued_work_order_ids` in backend order and match returned work orders; no local urgency sort or automatic frontend dispatch on escalation. Paged and awaiting_confirmation are valid work statuses. Approved fixtures are unchanged; PR60 examples exist only in tests.
