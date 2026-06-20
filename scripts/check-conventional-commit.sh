#!/usr/bin/env bash
# Enforce Conventional Commits format on the commit message.
# Called by pre-commit at the commit-msg stage (via .githooks-v1/commit-msg shim).
#
# Accepted format: type(scope)!: description
# Required types:  feat | fix | refactor | docs | test | chore |
#                  build | ci | perf | style | revert
#
# Scope is optional. The breaking-change marker (!) is optional.
# The description must be non-empty.
#
# Git-generated merge commits ("Merge …") and revert commits ("Revert …")
# are passed through unconditionally.
#
# CLAUDE.md mandates conventional commits; this gate is the machine
# enforcement of that policy.

set -euo pipefail

COMMIT_MSG_FILE="${1:?Usage: $0 <commit-msg-file>}"
FIRST_LINE="$(head -n1 "${COMMIT_MSG_FILE}")"

# Allow git-generated merge commits.
if [[ "${FIRST_LINE}" =~ ^Merge[[:space:]] ]]; then
    exit 0
fi

# Allow git-generated revert commits.
if [[ "${FIRST_LINE}" =~ ^Revert[[:space:]] ]]; then
    exit 0
fi

# Allow comment-only messages (e.g. --allow-empty with just # lines).
if [[ "${FIRST_LINE}" =~ ^# ]]; then
    exit 0
fi

PATTERN='^(feat|fix|refactor|docs|test|chore|build|ci|perf|style|revert)(\([^)]+\))?(!)?: .+'

if ! echo "${FIRST_LINE}" | grep -qE "${PATTERN}"; then
    echo "" >&2
    echo "[commit-msg] REJECTED: commit message does not follow Conventional Commits." >&2
    echo "[commit-msg]   Expected : type(scope)?: description" >&2
    echo "[commit-msg]   Types    : feat|fix|refactor|docs|test|chore|build|ci|perf|style|revert" >&2
    echo "[commit-msg]   Got      : ${FIRST_LINE}" >&2
    echo "" >&2
    exit 1
fi

exit 0
