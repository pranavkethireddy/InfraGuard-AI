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
| `fixture` (default) | Serves the approved contract fixtures in `src/api/fixtures/contracts/` verbatim through the same typed client (404 for anything without a fixture). A persistent "Fixture preview — illustrative data, not live" banner is shown. Incident status changes and simulations are disabled with an explanation. |
| `live` | Calls `VITE_API_BASE_URL` (default `http://localhost:8000/api/v1`). Errors (`{error:{code,message,details,request_id}}`, HTTP 404/409/422/503 or network) are shown with the request ID. **There is never a fallback to fixtures.** |

The FastAPI backend must allow CORS from the dev origin (`http://localhost:5173`).
`VITE_*` values are bundled into the browser — never put secrets in them.

## Fixtures

`src/api/fixtures/contracts/*.json` are exact copies of `contracts/fixtures/` in the main repo.
`src/api/fixtures/index.ts` checks them against the TypeScript contracts at compile time; `src/test/fixtures.test.ts` checks enum values at runtime.
`model.evaluated.example.json` is used only in tests and is never displayed as a measured result.

## Tooling

- `package-lock.json` is committed; use `npm ci` in CI.
- Vitest 4.1.12+ (no tinypool dependency; `npm audit` reported 0 vulnerabilities at export time).

## Routes

`/`, `/assets`, `/assets/:id`, `/simulate`, `/incidents`, `/incidents/:id`, `/models`.

## Contract rules

- All risk levels, scores, costs, impact and priority values are displayed exactly as the API returns them; the browser never computes them.
- `heuristic` and `model_score` values are labelled "not a probability"; only `calibrated_probability` is called a probability.
- Models without returned metrics show "Not evaluated" (or "not applicable" for rules). No metrics are invented.
- Impact assumptions are read-only (editing deferred). There is no approve/handoff action.
- Simulations: `POST /simulations`, recovery via `GET /simulations?status=running&asset_id=`, polling `GET /simulations/{id}` at `tick_seconds`, `POST /simulations/{id}/reset`. A 409 shows "already running".

## Layout

```
src/api/        typed client (client.ts), contracts (types.ts), queries (queries.ts), fixtures/*.json
src/components/ shell, badges, charts, model card
src/lib/router-adapter.tsx  router-neutral link used by pages
src/pages/      one component per route
src/App.tsx     react-router-dom routes
```
