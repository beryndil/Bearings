"""`CREDITS.md` must mention every runtime dependency.

Bearings ships with a Credits row in the About settings pane that
links to `CREDITS.md` on `main`. The list inside `CREDITS.md` is
hand-curated — friendly project names, links to homepages, brief
notes — so it can't be regenerated mechanically without losing
that polish. The risk this test guards against is the obvious one:
a contributor adds a runtime dependency to `pyproject.toml` or
`frontend/package.json` and forgets to credit it here.

The check is a substring assertion — `pyproject.toml`'s
`[project].dependencies` and `frontend/package.json`'s
`dependencies` (NOT devDependencies; build-time tooling doesn't
ship in the bundle and doesn't belong in user-facing credits) must
each appear somewhere in `CREDITS.md`. Each entry in the curated
list ends with the package identifier in backticks (e.g.
`` (`fastapi`) ``) so this assertion is easy to satisfy without
mangling the prose.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
FRONTEND_PACKAGE = REPO_ROOT / "frontend" / "package.json"
CREDITS = REPO_ROOT / "CREDITS.md"

# A PEP 508 dependency string looks like `name>=1.0` or
# `name[extra]>=1.0` or `name; python_version<'3.13'`. We only want
# the bare distribution name to use as a substring search. This
# regex pulls the name token off the front, stopping at any of the
# legal delimiters that follow it.
_PEP508_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def _pyproject_runtime_deps() -> list[str]:
    """Names of every runtime dependency in `pyproject.toml`.

    Only `[project].dependencies` — the `dev` group in
    `[dependency-groups]` is build-time tooling (pytest, mypy,
    ruff) and doesn't ship with the running app, so it doesn't
    belong in user-facing credits.
    """
    with PYPROJECT.open("rb") as fh:
        data = tomllib.load(fh)
    raw_deps = data["project"]["dependencies"]
    names: list[str] = []
    for spec in raw_deps:
        match = _PEP508_NAME.match(spec)
        if match is None:
            raise AssertionError(f"unparseable dependency spec: {spec!r}")
        names.append(match.group(1))
    return names


def _frontend_runtime_deps() -> list[str]:
    """Names of every runtime dependency in `frontend/package.json`.

    `devDependencies` (Vite, TypeScript, Vitest, etc.) is build/test
    tooling — same exclusion logic as the backend.
    """
    pkg = json.loads(FRONTEND_PACKAGE.read_text())
    return list(pkg.get("dependencies", {}).keys())


def test_credits_mentions_every_python_runtime_dep() -> None:
    """Every `pyproject.toml` runtime dep must appear in `CREDITS.md`.

    If this fails after adding a backend dependency, add a row to
    `CREDITS.md` under "Backend (runtime)" with the package name in
    backticks. The Settings → About → Credits link out to
    `CREDITS.md` is what users see; this test keeps the manifest
    and the user-facing list aligned.
    """
    credits_text = CREDITS.read_text()
    missing = [name for name in _pyproject_runtime_deps() if name not in credits_text]
    assert not missing, (
        f"CREDITS.md is missing entries for: {missing}. Add a row "
        "under 'Backend (runtime)' for each, with the package name "
        "in backticks so this drift-guard finds it."
    )


def test_credits_mentions_every_frontend_runtime_dep() -> None:
    """Every `frontend/package.json` runtime dep must appear too.

    Same recipe as the Python check — `package.json.dependencies`
    only, never `devDependencies`. Build tooling stays out of
    user-facing credits.
    """
    credits_text = CREDITS.read_text()
    missing = [name for name in _frontend_runtime_deps() if name not in credits_text]
    assert not missing, (
        f"CREDITS.md is missing entries for: {missing}. Add a row "
        "under 'Frontend (shipped in the bundle)' for each, with "
        "the package name in backticks so this drift-guard finds it."
    )
