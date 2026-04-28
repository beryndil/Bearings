#!/usr/bin/env bash
# Wrapper that runs a frontend npm script ONLY when frontend/node_modules
# exists. At item 0.1 the frontend skeleton is config-only — npm install
# happens in item 2.1. Until then, every frontend pre-commit / CI hook
# short-circuits with a clear notice instead of failing on missing
# node_modules.
#
# Usage: scripts/frontend-tools.sh <npm-script-name>
#
# Example:
#     scripts/frontend-tools.sh lint   # → cd frontend && npm run lint
set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "usage: $0 <npm-script-name>" >&2
    exit 2
fi

readonly script_name="$1"
readonly frontend_dir="$(cd "$(dirname "$0")/.." && pwd)/frontend"

if [[ ! -d "${frontend_dir}/node_modules" ]]; then
    echo "[frontend-tools] frontend/node_modules not present — skipping '${script_name}'."
    echo "[frontend-tools] (Item 2.1 will run 'npm install' and activate this gate.)"
    exit 0
fi

cd "${frontend_dir}"
exec npm run --silent "${script_name}"
