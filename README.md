# School Safety & Resilience Digital Twin
### Okul Güvenliği ve Dayanıklılığı Dijital İkizi

A research-oriented, **deterministic system-dynamics simulation** of a school *as an
institution*: its physical/environmental conditions, social climate, organisational
processes and support capacity. Users manipulate variables and causal assumptions, configure
intervention scenarios, run monthly simulations, compare them against a baseline, quantify
parameter uncertainty and sensitivity, calibrate against aggregate data, validate the model,
and inspect an illustrative 3D school linked to the simulation outputs.

> **SYNTHETIC DEMONSTRATION DATA — NOT REAL SCHOOL MEASUREMENTS.**
> All default coefficients are **illustrative** assumptions. Outputs are institutional
> readiness and process indicators — **never** probabilities of violence, attack or harm,
> and never individual-level predictions, profiles or risk scores.

## What it does

| Capability | Where |
|---|---|
| 16 variables in 4 domains, model-calculated / manual-override modes | Variables page, `backend/config/model_config.json` |
| Editable causal graph (H1–H10 + supporting relationships, evidence classes, loops R1/B1, custom edges) driving the same matrices the simulator uses | Causal Model page |
| Deterministic monthly engine: `X(t+1) = clip[X + Λ(X* − X)]`, `X* = clip[b + AX + ΓZ + ΠY + BU + GD]` | `backend/twin_engine/simulator.py` |
| Stock-flow support-process block with capacity constraint and mass balance | Lab → Stock & flow |
| Domain indices ENV/SOC/ORG/SUP, TOTAL and MIN_DOMAIN | everywhere |
| What-if scenarios S0–S4 + custom; schedules with start/ramp/end; comparison vs baseline with comparability checks and resource requirements | Simulation Lab, Scenario Library |
| Uncertainty (Latin hypercube, P5/P50/P95, paired baseline differences) | Advanced Analytics |
| Sensitivity (SALib Morris & Sobol, tornado, heatmap) with run-count safeguards | Advanced Analytics |
| Calibration: regularised least squares + Bayesian adaptive Metropolis (R̂, ESS) | Advanced Analytics |
| Verification (13 automated checks incl. full-map stability), conceptual/historical/intervention validation, envelope, exportable report | Advanced Analytics → Validation |
| Synthetic data generator, CSV/JSON import with mapping and privacy guard, quality reports | Data & Research |
| Interactive low-poly 3D school (floors, departments, linked indicators, before/after) with 2D fallback | 3D Digital Twin |
| Turkish (default) and English UI | language switch, top right |
| Live documentation generated from the configuration | Model Documentation |

## Quick start (local)

Requirements: Python 3.11+ (tested 3.13), Node.js 20+ (tested 22).

```bash
scripts/dev.sh
```

This creates `backend/.venv`, installs dependencies, starts the engine on
`http://127.0.0.1:8000` and the web app on `http://localhost:3000`.

Manual start:

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
```

```bash
cd backend && .venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

Or with containers:

```bash
docker compose up --build
```

## Hosted deployment

**Vercel (one project, two services)** — `vercel.json` at the repository root defines a
`frontend` service (Next.js, `frontend/`) and a `backend` service (FastAPI, `backend/`,
entrypoint `api.main:app`). Requests to `/api/*` go to the backend, everything else to the
frontend, on one domain; the browser only calls same-origin `/api/*`. Import the repository
with the project root at the repository root and test locally with `vercel dev`.
Vercel installs backend dependencies from `backend/pyproject.toml`, which drops SALib's
unused matplotlib dependency (`tool.uv.override-dependencies`) to stay under the function
size limit; `backend/requirements.txt` (Docker, local dev) must list the same packages.
On Vercel the SQLite store lives in `/tmp`, which is per instance and not durable: saved
scenarios and model edits can disappear on cold starts until a hosted database is added.

**Alternative (separate hosts)** — deploy `backend/Dockerfile` (build context = repository
root; `render.yaml` is a Render blueprint with a persistent disk) and run the frontend with
`BACKEND_URL` set to the engine URL; Next.js then proxies `/api/*` to it.

The workspace id sent by browsers separates scenario libraries but is **not authentication**;
add access control before importing authorised school data (see `docs/DATA_GOVERNANCE.md`).

## Tests

```bash
scripts/test_all.sh
```

| Suite | Command | Count |
|---|---|---|
| Engine, analytics, API (pytest) | `cd backend && .venv/bin/python -m pytest -q` | 91 |
| Frontend units (vitest) | `cd frontend && npx vitest run` | 15 |
| Type check | `cd frontend && npx tsc --noEmit` | — |
| End-to-end (Playwright, real stack) | `cd frontend && npx playwright test --trace off` | 5 specs |

The end-to-end suite runs the complete research workflow: load synthetic data → change
variables in all four domains → edit a causal coefficient → create a scenario → run a
12-month simulation → compare with baseline → inspect charts → inspect the 3D school →
export results → reload and verify persistence.

## Repository layout

```text
backend/
  config/          authoritative model configuration, scenario templates, reference registry
  twin_engine/     simulation engine and analytics (no web dependencies)
  api/             FastAPI service + SQLite persistence
  tests/           pytest suites
frontend/
  app/             Next.js pages (overview, twin, variables, causal, lab, scenarios, analytics, data, docs)
  components/      UI primitives, charts, 3D scene, editors
  lib/             API client, store, i18n (tr/en), zones, formatting
  e2e/, tests/     Playwright and vitest suites
docs/              model, variables, causal assumptions, equations, parameters, governance,
                   validation, architecture, limitations
scripts/           dev/test runners, baseline anchoring, documentation generator
```

## Documentation

| Document | Content |
|---|---|
| [MODEL_SPECIFICATION](docs/MODEL_SPECIFICATION.md) | purpose, boundaries, structure, scenarios, scope of use |
| [VARIABLE_DICTIONARY](docs/VARIABLE_DICTIONARY.md) | all 16 variables, measurement, bounds, evidence (generated) |
| [CAUSAL_ASSUMPTIONS](docs/CAUSAL_ASSUMPTIONS.md) | H1–H10, evidence classes, loops, relationship table |
| [MATHEMATICAL_EQUATIONS](docs/MATHEMATICAL_EQUATIONS.md) | every equation, timing, stability, analysis layers |
| [PARAMETER_REGISTRY](docs/PARAMETER_REGISTRY.md) | every parameter with range and provenance (generated) |
| [DATA_GOVERNANCE](docs/DATA_GOVERNANCE.md) | data classes, privacy guard, KVKK context, hosting |
| [VALIDATION_PROTOCOL](docs/VALIDATION_PROTOCOL.md) | verification checks, calibration diagnostics, validation steps |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | components, principles, persistence, testing, deployment |
| [LIMITATIONS](docs/LIMITATIONS.md) | what the model cannot do and known weaknesses |

After changing `backend/config/model_config.json`, regenerate the derived documentation:

```bash
backend/.venv/bin/python scripts/generate_docs.py
```

## Responsible use

This software supports institutional prevention research and planning. It must not be used to
make decisions about individual students, for security or tactical planning, or to claim that
an intervention works without proper evaluation. Research on targeted school violence finds no
accurate student "profile" (Vossekuil et al., 2002; National Threat Assessment Center, 2019) —
the model is deliberately designed at the institutional level.
