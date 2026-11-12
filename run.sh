#!/usr/bin/env bash
# One command to set up and run everything (macOS / Linux / WSL).  ./run.sh
set -e
cd "$(dirname "$0")"

command -v python3 >/dev/null || { echo "Python 3.10+ is required: https://www.python.org/downloads/"; exit 1; }
command -v node    >/dev/null || { echo "Node.js 18+ is required: https://nodejs.org"; exit 1; }
command -v pnpm    >/dev/null || { echo "pnpm is required. Run:  npm install -g pnpm   (or: corepack enable)"; exit 1; }
command -v ffmpeg  >/dev/null || echo "WARNING: ffmpeg not found. Install it (macOS: brew install ffmpeg, Ubuntu: sudo apt install ffmpeg)."

echo "==> Backend setup"
cd backend
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
cd ..

echo "==> Frontend setup"
(cd frontend && pnpm install)

cleanup() { echo; echo "Stopping..."; kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "==> Starting backend on http://127.0.0.1:8000"
(cd backend && . .venv/bin/activate && python run.py) &

echo "==> Starting frontend on http://localhost:5173  (open this one)"
(cd frontend && pnpm dev --host 127.0.0.1) &

wait
