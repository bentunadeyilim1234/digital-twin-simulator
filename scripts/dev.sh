#!/usr/bin/env bash
# Start the engine (port 8000) and the web app (port 3000) for local development.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements-dev.txt
fi
.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT
cd "$ROOT/frontend"
[ -d node_modules ] || npm install --no-audit --no-fund
npm run dev
