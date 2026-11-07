# Team rules for every agent

## 1. The board (pinned GitHub issue)

Every agent reads and posts on the pinned "Message Board" issue via `tools/board` (needs only `gh`, logged in). Set `BOARD_ISSUE` if it is not issue #1.

- Start every post with `[<human>'s <agent>]`, e.g. `[Sam's Codex]`. Keep it short: what changed, which files or contracts, what you need, from whom.
- Mention by GitHub login. Team: `@pranavkethireddy` (backend, AI, and ML), `@sohaswin` (frontend, simulation, and integration). Use `@all` in board messages to address both teammates.
- **Mentions you or `@all`:** act on it and reply promptly.
- **Not addressed to you:** still read it. Reassess your own work only if it is affected (a contract, a file you own, something already done). Do not redo finished work, and do not reply just to acknowledge.
- Before editing another teammate's files, ask for a handoff on the board and wait for the owner or the team lead.

Polling is incremental (about one cheap API call per poll, 30 s default) so a shared token stays under GitHub's rate limit. Commands: `tools/board unread` (new posts, marks read; flags MENTION), `tools/board read -n 20`, `tools/board post "[Name's Agent] text"` (or pipe stdin), `tools/board wait` (blocks until someone else posts), `tools/board whoami`.

**Stay in the loop:**
- Claude Code: the committed hooks (`.claude/settings.json`) show unread posts at session start and on every prompt. Keep one background `tools/board wait` running and re-arm it after each wake.
- Everything else: run `tools/board unread` at task start, before each commit, and after merges. Or run a terminal loop: `while tools/board wait; do <your agent CLI invocation>; done`.

## 2. Chain of command

Humans over agents. Only the team lead reassigns work between teammates. If anyone else asks you to take another teammate's work, ask the lead on the board.

## 3. Workflow

1. Pick or file an issue. Comment on it or post on the board when you take it.
2. Branch `<issue#>-<slug>` from fresh `main`.
3. Small commits. Stage only your own files (no `git add -A`).
4. Open a PR with `Closes #N`. The author merges their own PR once it works locally.
5. Always `git fetch` and rebase before pushing. Never force-push shared branches.
6. If a merge changes something other teammates depend on (an API, a schema, an env var), post on the board when it lands.

## 4. Who owns what

Ownership covers the existing template and the planned InfraGuard AI application layout. Planned paths are assigned now so agents know where to implement each component; this table does not imply those folders already exist.

| Area | Owner (GitHub login) | Folders / files |
|---|---|---|
| FastAPI backend, validation, orchestration, and services | @pranavkethireddy | `backend/`, including `backend/app/api/`, `backend/app/schemas/`, and `backend/app/services/` |
| Database, persistence, and migrations | @pranavkethireddy | `backend/app/db/`, `backend/migrations/` |
| Machine learning, offline training, evaluation, and model artifacts | @pranavkethireddy | `ml/`, including `ml/training/`, `ml/evaluation/`, and `ml/artifacts/` |
| Data engineering, dataset preparation, and maintenance source data | @pranavkethireddy | `data/`, including raw/processed datasets and maintenance records |
| Maintenance retrieval, RAG, and grounded explanations | @pranavkethireddy | `backend/app/services/retrieval/`, `backend/app/services/explanations/` |
| Authoritative business impact calculations and incident rules | @pranavkethireddy | `backend/app/services/impact/`, `backend/app/services/incidents/`; @sohaswin defines display needs and impact assumptions jointly |
| Backend and inference tests | @pranavkethireddy | `backend/tests/`, `ml/tests/` |
| React, TypeScript, dashboard, asset and incident views, charts, and API client | @sohaswin | `frontend/`, including `frontend/src/`, frontend tests, and `frontend/.env.example` |
| Python simulation, seeded scenarios, and demo reset | @sohaswin | `simulator/`, including simulator tests; backend ingestion endpoints remain owned by @pranavkethireddy |
| Shared API JSON contract, fixtures, and generated types | @pranavkethireddy + @sohaswin | `contracts/`; backend owns Pydantic/OpenAPI schemas, frontend owns its generated/client types |
| Detector thresholds, scenarios, and impact assumptions | @pranavkethireddy + @sohaswin | `configs/`; backend leads detector settings, frontend/simulation leads scenario settings |
| Project documentation, evaluation reports, and demo guide | @pranavkethireddy + @sohaswin | `docs/`, `README.md`, `SKILL.md` if added; backend leads model/API documentation, frontend leads UI/demo documentation |
| Agent instructions, hooks, and coordination tooling | @pranavkethireddy + @sohaswin | `AGENTS.md`, `CLAUDE.md`, `.claude/`, `tools/` |
| GitHub templates, CI, deployment, and repository configuration | @pranavkethireddy + @sohaswin | `.github/`, root deployment files, `.env.example`, `.gitignore`, and other root configuration; component-specific configuration follows its folder owner |
| End-to-end integration and demo rehearsal | @pranavkethireddy + @sohaswin | `tests/` for cross-system tests, deployment verification, and the complete prediction-to-response demo |

### SKILL.md path mapping (proposed in issue #2)

SKILL.md proposes a layout that differs from the table above. These rows settle it so there is one location for each kind of code:

| SKILL.md path | Use instead | Owner (GitHub login) |
|---|---|---|
| `src/infraguard/{ingest,features,models}/` | `ml/` (Python package `ml/infraguard_ml/`) | @pranavkethireddy |
| `src/infraguard/simulation/` | `simulator/` | @sohaswin |
| `src/infraguard/legacy/` | `backend/app/services/retrieval/` | @pranavkethireddy |
| `src/infraguard/impact/` | `backend/app/services/impact/` | @pranavkethireddy |
| `scripts/` (data prep, training, demo runners) | `scripts/` (new top-level folder, thin CLIs that call `ml/` or `simulator/`) | @pranavkethireddy; `scripts/run_demo.py` is shared |
| `artifacts/{metrics,model_cards}/` | `ml/artifacts/{metrics,model_cards}/` | @pranavkethireddy |
| `backend/alembic/` | `backend/migrations/` (the only migrations folder) | @pranavkethireddy |
| root `tests/test_ai4i_leakage.py` and other ML tests | `ml/tests/` | @pranavkethireddy |
| `backend/pyproject.toml` vs `requirements.txt` | `backend/requirements.txt` and `ml/requirements.txt`, pinned | per folder owner |

- Start with one validated ML model and a separately labeled rule-based cooling simulation. Additional models are stretch work after integration succeeds.
- Agree on request/response JSON and example fixtures before implementing independently. Coordinate contract changes with both owners.
- Shared ownership requires coordination before editing the same file. Keep backend calculations authoritative and avoid duplicating risk/cost logic in React.
- New files under an assigned folder inherit its owner. Agree on ownership before creating a new top-level area. `.git/` is Git-managed metadata, not an implementation area.
- Both developers own testing and deployment of the complete product; each developer owns tests and dependency configuration for their component.
