#!/usr/bin/env bash
# Pre-commit branch-verifier — rejects commits to any branch other than v1-rebuild.
#
# Wired into .pre-commit-config.yaml as a `local` hook with `always_run: true`.
# Done-when criterion #10 of master item 521. Acceptance test:
#
#     git checkout -b __branch_verifier_test_branch__
#     git commit --allow-empty -m 'should fail' || echo OK_REJECTED
#
# Must print OK_REJECTED on a non-v1-rebuild branch.
set -euo pipefail

readonly EXPECTED_BRANCH="v1-rebuild"

current_branch="$(git symbolic-ref --short HEAD 2>/dev/null || echo "(detached)")"

if [[ "${current_branch}" != "${EXPECTED_BRANCH}" ]]; then
    cat >&2 <<EOF
[branch-verifier] Refusing to commit on branch '${current_branch}'.
[branch-verifier] The v1 rebuild only accepts commits on '${EXPECTED_BRANCH}'.
[branch-verifier] If you genuinely need a side branch, document the reason in
[branch-verifier] TODO.md first and then bypass with --no-verify (audited).
EOF
    exit 1
fi

exit 0
