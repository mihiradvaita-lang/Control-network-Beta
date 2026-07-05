#!/usr/bin/env bash
# Control Network — Triage Copilot (MVP). One-command local run.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1   # ZDR: no .pyc on disk

if [ ! -d ".venv" ]; then
  echo "[CN] creating virtualenv..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt
[ -f .env ] || cp .env.example .env
PORT="${CN_PORT:-8000}"
echo "[CN] starting on http://localhost:${PORT}  (Ctrl+C to stop)"
# Security default: bind loopback only (matches CN_HOST default in app/config.py).
# Override with CN_HOST=0.0.0.0 to expose on the LAN (a ZDR tool should not by default).
HOST="${CN_HOST:-127.0.0.1}"
exec uvicorn app.main:app --host "${HOST}" --port "${PORT}"
