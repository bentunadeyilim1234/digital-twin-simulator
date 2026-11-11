#!/usr/bin/env bash
# Run every automated test: engine/API (pytest), frontend units (vitest), type check, e2e (Playwright).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
(cd "$ROOT/backend" && .venv/bin/python -m pytest -q)
(cd "$ROOT/frontend" && npx tsc --noEmit && npx vitest run && npx playwright test --trace off)
