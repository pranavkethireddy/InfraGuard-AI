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
| `live` (default) | Calls `VITE_API_BASE_URL` (default `http://localhost:8000/api/v1`). Errors (`{error:{code,message,details,request_id}}`, HTTP 404/409/422/503 or network) are shown with the request ID. **There is never a fallback to fixtures.** |

The FastAPI backend must allow CORS from the dev origin (`http://localhost:5173`).
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

For a local iPad on the same Wi-Fi, configure your existing backend/frontend yourself (these steps do not change server settings):

1. Run FastAPI with `--host 0.0.0.0`; include the frontend LAN origin, e.g. `http://192.168.1.20:5173`, in backend `CORS_ORIGINS`.
2. Set `VITE_API_BASE_URL=http://LAN_IP:8000/api/v1` and `VITE_DATA_MODE=live` in your local frontend environment (replace LAN_IP with the laptop address).
3. Run `npm --prefix frontend run dev -- --host 0.0.0.0` and open `http://LAN_IP:5173/pager?technician=tech-03` on the iPad. Restrict access to your trusted local network; this is not deployment or authentication.

Pager controls have 44px+ touch targets, keyboard focus, and locally scrolling tables for portrait/landscape. Community impact #44 is not implemented because its contract is not approved.

`/servers/:id?gpu=returnedIndex` drills from returned rack `server_ids` to the actual server/GPU index. `GET /fleet/servers/{encodedId}?history=30` polls every second with a distinct server query key. GPUs, online/power state, PSU redundancy, ECC, cooling, incident links and job reasons/prices are returned values only. GPU histories use only provided per-GPU fields; nulls are Not reported. Overview/Fleet jobs come from `FleetMap.jobs` (the jobs fixture is an excerpt, not a separate endpoint). GPU rule scores are heuristic, not probabilities. Targeted fault POSTs are explicit `{asset_ids:[id],site:"datacenter",count:1}`; the backend chooses the kind. Pending backend deployment can return 404/503 with a request ID; no live fallback. GPU-hour prices are demo assumptions, not bills.

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
