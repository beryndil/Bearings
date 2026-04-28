#!/usr/bin/env bash
# One-shot setup for a fresh checkout of the v1-rebuild worktree.
#
# This worktree shares its parent .git directory with the v0.17.x main
# worktree at /home/beryndil/Projects/Bearings/. Without isolation, any
# pre-commit installation here would write into the shared .git/hooks/ and
# disrupt v0.17.x. We isolate via:
#
#   1. extensions.worktreeConfig=true  (parent .git/config flag)
#   2. core.hooksPath=<this worktree>/.githooks-v1  (per-worktree)
#
# The hook script under .githooks-v1/ is checked into version control and
# is a thin shim around `pre-commit hook-impl` (mirroring what
# `pre-commit install` writes — installed manually because pre-commit
# refuses to write into a hooks dir when core.hooksPath is set).
#
# Idempotent: re-running this script is safe.
set -euo pipefail

readonly REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_ROOT}"

readonly PARENT_GIT_DIR="$(git rev-parse --git-common-dir)"
readonly EXPECTED_HOOKS_PATH="${REPO_ROOT}/.githooks-v1"

# Step 1 — enable per-worktree config in the shared .git/config.
git -C "${PARENT_GIT_DIR}/.." config extensions.worktreeConfig true

# Step 2 — pin this worktree's hooks dir.
git config --worktree core.hooksPath "${EXPECTED_HOOKS_PATH}"

# Step 3 — sanity-check the hook script is present and executable.
if [[ ! -x "${EXPECTED_HOOKS_PATH}/pre-commit" ]]; then
    echo "[setup-worktree] Missing or non-executable hook: ${EXPECTED_HOOKS_PATH}/pre-commit" >&2
    echo "[setup-worktree] This file is checked in; if you see this, the git checkout is broken." >&2
    exit 1
fi

# Step 4 — make sure the dev environment exists.
if [[ ! -x "${REPO_ROOT}/.venv/bin/python" ]]; then
    echo "[setup-worktree] Bootstrapping uv dev environment..."
    uv sync --extra dev
fi

echo "[setup-worktree] OK."
echo "[setup-worktree]   core.hooksPath = $(git config --worktree core.hooksPath)"
echo "[setup-worktree]   extensions.worktreeConfig = $(git -C "${PARENT_GIT_DIR}/.." config extensions.worktreeConfig)"
