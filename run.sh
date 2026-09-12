#!/usr/bin/env bash
# Signals — start the personal health analytics app.
#
#   ./run.sh dev     backend (:8000) + Vite dev server (:5173, hot reload)
#   ./run.sh serve   build frontend, then serve everything from :8000
#   ./run.sh sync     one-off real Google Health sync
#
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate

case "${1:-dev}" in
  dev)
    echo "Backend  → http://127.0.0.1:8000"
    echo "Frontend → http://127.0.0.1:5173  (öffne diese)"
    python -m backend.api.main &
    BACK=$!
    trap 'kill $BACK 2>/dev/null' EXIT
    npm run dev --prefix frontend
    ;;
  serve)
    echo "Baue Frontend…"
    npm run build --prefix frontend
    echo "Alles unter http://127.0.0.1:8000"
    python -m backend.api.main
    ;;
  sync)
    python -c "import asyncio; from backend.database import DataMode; from backend.services.sync import run_sync; print(vars(asyncio.run(run_sync(DataMode.REAL))))"
    ;;
  *)
    echo "usage: ./run.sh [dev|serve|sync]"; exit 1 ;;
esac
