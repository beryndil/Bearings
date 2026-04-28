#!/usr/bin/env bash
# Wrapper that runs lychee against passed markdown files when the binary is
# available locally, and skips with a clear notice otherwise.
#
# Why not the official pre-commit-hook? Lychee's official repo only ships a
# Docker-based hook; pulling the image on every developer machine is heavy
# and the localhost-only Bearings dev loop doesn't justify it. CI installs
# lychee directly via the lycheeverse/lychee-action GitHub Action.
set -euo pipefail

if ! command -v lychee >/dev/null 2>&1; then
    echo "[lychee] not installed locally — skipping (CI will run it)."
    exit 0
fi

if [[ $# -eq 0 ]]; then
    exit 0
fi

# --no-progress to keep pre-commit output quiet; --offline-only would skip
# real link checks, so we use --max-retries 1 + --timeout 10 instead to fail
# fast on flaky links while still validating reachable ones.
exec lychee --no-progress --max-retries 1 --timeout 10 "$@"
