"""`bearings check` — re-run steps 2, 3, 5 and update `state.toml`.

Cheap revalidation for an existing `.bearings/`. Does not touch
`manifest.toml` (identity) or `pending.toml` (the user's in-flight
record). Only `state.toml` gets rewritten, bumping
`environment.last_validated`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from bearings.bearings_dir.io import (
    MANIFEST_FILE,
    STATE_FILE,
    bearings_path,
    read_toml_model,
    write_toml_model,
)
from bearings.bearings_dir.onboard import (
    step_environment,
    step_git_state,
    step_unfinished,
)
from bearings.bearings_dir.schema import EnvironmentBlock, Manifest, State


def run_check(directory: Path) -> State:
    """Re-run steps 2/3/5 and persist the refreshed `state.toml`.

    Returns the new `State`. Raises `FileNotFoundError` when the
    directory hasn't been onboarded yet — the caller should prompt
    the user to run `bearings here init` first.
    """
    directory = directory.resolve()
    bearings_root = bearings_path(directory)
    manifest_path = bearings_root / MANIFEST_FILE
    if not manifest_path.exists():
        raise FileNotFoundError(f"{manifest_path} not found — run `bearings here init` first.")

    # Load (but don't require) the existing state so we preserve
    # `last_session_id` across checks.
    state_path = bearings_root / STATE_FILE
    prior = read_toml_model(state_path, State)
    prior_session_id = prior.last_session_id if prior is not None else None

    git = step_git_state(directory)
    env = step_environment(directory)
    # Step 5 is run but its output goes into the notes rather than
    # `state.toml` proper — the narrative read is ephemeral by design.
    unfinished = step_unfinished(directory)

    notes: list[str] = list(env.get("notes", []))
    if unfinished.get("todo_hits"):
        notes.append(f"{len(unfinished['todo_hits'])} unfinished markers in tree")
    for finding in unfinished.get("naming_findings", []):
        notes.append(
            f"naming note: '{finding['variant']}' in {finding['file']} "
            f"(canonical '{finding['canonical']}')"
        )

    environment = EnvironmentBlock(
        venv_path=env.get("venv_path"),
        lockfile_fresh=env.get("lockfile_fresh"),
        notes=notes[:16],  # hard-cap so a noisy tree doesn't blow the 800-token brief budget
        last_validated=datetime.now(UTC),
    )

    state = State(
        branch=git.get("branch"),
        dirty=git.get("dirty"),
        environment=environment,
        last_session_id=prior_session_id,
    )
    write_toml_model(state_path, state)
    return state


def manifest_exists(directory: Path) -> bool:
    """True when `.bearings/manifest.toml` exists and parses cleanly."""
    path = bearings_path(directory) / MANIFEST_FILE
    return read_toml_model(path, Manifest) is not None


__all__ = ["manifest_exists", "run_check"]
