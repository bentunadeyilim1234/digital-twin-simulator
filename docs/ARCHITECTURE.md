# Architecture

```text
 Browser (Next.js client components, TR/EN)        Next.js server (Vercel / node)
 ┌──────────────────────────────────────────┐       ┌─────────────────────────────┐
 │ Overview · 3D Twin · Variables · Causal  │  /api │ rewrites /api/* → BACKEND_URL│
 │ Lab · Scenarios · Analytics · Data · Docs │──────▶│ (same-origin, no CORS)       │
 │ zustand store · Recharts · R3F (lazy)    │       └──────────────┬──────────────┘
 └──────────────────────────────────────────┘                      │ HTTP/JSON
                                                                    ▼
                         FastAPI (backend/api) — thin layer, workspace-scoped
                         ┌───────────────────────────────────────────────────┐
                         │ main.py: model · edges · parameters · scenarios ·  │
                         │ simulate/compare · analytics · datasets · exports  │
                         │ db.py: SQLite (workspaces, scenarios, datasets,    │
                         │        runs)                                       │
                         └──────────────────────┬────────────────────────────┘
                                                │ Python calls
                         twin_engine (backend/twin_engine) — single source of maths
                         ┌───────────────────────────────────────────────────┐
                         │ schemas · config · normalization · params         │
                         │ model (matrix compilation, stability)             │
                         │ scenarios (resolution, schedules, comparability)   │
                         │ simulator (step(), run(), full-map Jacobian)       │
                         │ indices · anchoring · equations · graph            │
                         │ synthetic · datasets · uncertainty · sensitivity   │
                         │ calibration · validation                           │
                         └──────────────────────┬────────────────────────────┘
                                                │ reads
                         config/model_config.json · scenario_templates.json · references.json
```

## Principles

1. **One authoritative configuration.** Variables, relationships, parameters, loops and
   templates live in `config/`. The simulator, causal graph, variables page, parameter
   registry, equations and generated documentation all read it.
2. **One implementation of the mathematics.** `twin_engine` has no web dependencies. The
   frontend performs no model calculations: it formats numbers, maps values to colours, and
   computes the plain display mean used to tint 3D zones. Normalisation and raw-unit
   conversion are done by the engine (`/api/normalize`, `/api/denormalize`).
3. **Single transition function.** `simulator.step()` is the only implementation of the
   monthly update; `run()` iterates it and the stability analysis differentiates it.
4. **Fast re-parameterisation.** `compile_model()` maps every parameter id to one matrix
   cell (`param_slots`), so analysis layers patch compiled copies instead of re-validating
   the configuration (≈1 ms per 36-month run).
5. **Outer layers are separate.** Randomness exists only in synthetic data, LHS sampling,
   Morris/Sobol sampling and MCMC — always seeded.

## Persistence

SQLite (`TWIN_DB_PATH`, default `backend/data/twin.sqlite3`): one row per workspace holding
its model configuration, plus scenarios, datasets and saved runs (last 150 per workspace).
The browser keeps a random workspace id in `localStorage`; new workspaces are seeded
atomically with S0–S4 and a synthetic dataset.

## Frontend

- Next.js 16 App Router, TypeScript, Tailwind 4, Radix primitives styled shadcn-style.
- `lib/i18n` — centralised dictionaries; Turkish default; parity enforced by a unit test.
- `lib/store.ts` — zustand: config, scenarios, datasets, active scenario, last comparison.
- Charts: Recharts (single y-axis, crosshair tooltips, P5–P95 range bands, table view toggle);
  validated dark categorical palette; scenario colours follow the entity, not rank.
- 3D: React Three Fiber + drei, `frameloop="demand"` (renders only on change), lazy-loaded via
  `next/dynamic`; 2D SVG fallback when WebGL is unavailable.

## Testing

| Layer | Tool | Location |
|---|---|---|
| Engine & analytics | pytest (75) | `backend/tests/test_engine.py`, `test_analytics.py` |
| API & persistence | pytest + TestClient (13) | `backend/tests/test_api.py` |
| Frontend units | vitest + Testing Library (15) | `frontend/tests` |
| End-to-end | Playwright (5 specs, real stack) | `frontend/e2e` |

## Deployment

- **Frontend**: Vercel (root directory `frontend`, env `BACKEND_URL`), or `frontend/Dockerfile`.
- **Engine**: any container host (`backend/Dockerfile`; `render.yaml` blueprint with a
  persistent disk for SQLite), env `TWIN_ALLOWED_ORIGINS`, `TWIN_DB_PATH`.
- **Local**: `scripts/dev.sh`, or `docker compose up --build`.
