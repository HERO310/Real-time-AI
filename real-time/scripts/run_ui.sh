#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${1:-127.0.0.1}"
PORT="${2:-8501}"

cd "$ROOT_DIR"
streamlit run ui/app.py --server.address "$HOST" --server.port "$PORT" --server.headless true
