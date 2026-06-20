"""``bearings here`` subcommand — per-directory .bearings/ context.

Per ``docs/behavior/bearings-cli.md`` §"bearings here" the subcommand
exposes two sub-subcommands:

* ``init [--dir PATH]`` — run the onboarding ritual against the target
  directory, write ``.bearings/{manifest,state,pending}.toml``, and
  print ``Wrote .bearings/ to <root>`` on stdout.  Exit ``0``.
* ``check [--dir PATH]`` — re-validate the directory's environment +
  git state, bump ``state.toml.last_validated``, and print the
  revalidation summary.  Exit ``0``.  Failure: ``.bearings/`` missing
  → stderr with a ``FileNotFoundError`` message and exit ``1``.

Per arch §1.1.1 each handler body stays thin — one call into a domain
helper (:func:`_do_here_init` / :func:`_do_here_check`).
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from bearings.bearings_dir import io as bdir_io
from bearings.bearings_dir.onboarding import (
    dir_init_body,
    probe_env_status,
    probe_git_status,
)
from bearings.config.constants import (
    BEARINGS_DIR_MANIFEST_FILENAME,
    BEARINGS_DIR_STATE_FILENAME,
    BEARINGS_DIR_SUBDIR,
    CLI_EXIT_OK,
    CLI_EXIT_OPERATION_FAILURE,
)


def build_subparser(
    parent: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Wire the ``here`` subcommand and its two sub-subcommands into ``parent``."""
    here = parent.add_parser(
        "here",
        help="per-directory .bearings/ context (init, check)",
        description=(
            "Manage the per-directory ``.bearings/`` context store. "
            "``init`` runs the 7-step onboarding ritual and writes "
            "``.bearings/{manifest,state,pending}.toml``. "
            "``check`` re-validates the directory and bumps last_validated."
        ),
    )
    here_sub = here.add_subparsers(
        dest="here_subcommand",
        metavar="<here-subcommand>",
        required=True,
    )
    _build_init_parser(here_sub)
    _build_check_parser(here_sub)
    here.set_defaults(func=_dispatch_no_subcommand)


def _build_init_parser(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """``bearings here init`` — run the onboarding ritual."""
    parser = sub.add_parser(
        "init",
        help="run the onboarding ritual for the target directory",
        description=(
            "Run the 7-step onboarding ritual, write .bearings/manifest.toml, "
            ".bearings/state.toml, and .bearings/pending.toml. Idempotent."
        ),
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="target directory (default: CWD)",
    )
    parser.set_defaults(func=_cmd_here_init)


def _build_check_parser(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """``bearings here check`` — re-validate the directory context."""
    parser = sub.add_parser(
        "check",
        help="re-validate the directory environment and git state",
        description=(
            "Re-run environment + git state probes, bump last_validated in "
            "state.toml, and print the revalidation summary. Requires that "
            ".bearings/ already exists (run 'bearings here init' first)."
        ),
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="target directory (default: CWD)",
    )
    parser.set_defaults(func=_cmd_here_check)


# ---------------------------------------------------------------------------
# Sub-subcommand handlers (thin dispatchers)
# ---------------------------------------------------------------------------


def _cmd_here_init(args: argparse.Namespace) -> int:
    """Handler for ``bearings here init``."""
    return _do_here_init(_resolve_dir(args.dir))


def _cmd_here_check(args: argparse.Namespace) -> int:
    """Handler for ``bearings here check``."""
    return _do_here_check(_resolve_dir(args.dir))


def _dispatch_no_subcommand(args: argparse.Namespace) -> int:
    """Fallback when ``here`` receives no sub-subcommand."""
    del args
    sys.stderr.write("bearings here: missing sub-subcommand\n")
    return CLI_EXIT_OPERATION_FAILURE


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------


def _do_here_init(directory: Path) -> int:
    """Run the onboarding ritual and write ``.bearings/`` files.

    Calls :func:`~bearings.bearings_dir.onboarding.dir_init_body` which
    runs all seven onboarding steps and writes
    ``manifest.toml``, ``state.toml``, and ``pending.toml``.

    Stdout: ``Wrote .bearings/ to <directory>``.  Exit ``0`` on success;
    exit ``1`` on :exc:`OSError` (e.g. directory not writable).
    """
    try:
        dir_init_body(directory)
    except OSError as exc:
        sys.stderr.write(f"bearings here init: {exc}\n")
        return CLI_EXIT_OPERATION_FAILURE
    sys.stdout.write(f"Wrote .bearings/ to {directory}\n")
    return CLI_EXIT_OK


def _do_here_check(directory: Path) -> int:
    """Re-validate directory context and bump ``last_validated`` in state.toml.

    Requires ``.bearings/manifest.toml`` to exist — if absent, writes a
    ``FileNotFoundError`` message to stderr and exits ``1``.

    Stdout:
    * ``Revalidated <path>: branch <name>, <clean|dirty>.``
      (or ``Revalidated <path>: not a git repo.`` for non-git dirs)
    * ``last_validated = <iso8601>``
    * One additional line: the environment/lockfile status note.
    """
    bearings_dir = directory / BEARINGS_DIR_SUBDIR
    manifest_path = bearings_dir / BEARINGS_DIR_MANIFEST_FILENAME
    if not manifest_path.exists():
        sys.stderr.write(
            f"FileNotFoundError: .bearings/ not found in {directory}; "
            "run 'bearings here init' first\n"
        )
        return CLI_EXIT_OPERATION_FAILURE

    git_stat = probe_git_status(directory)
    env_stat = probe_env_status(directory)
    git_summary = _parse_git_summary(git_stat)

    now = datetime.now(UTC)
    last_validated_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Bump last_validated in state.toml.  We read/merge to preserve existing
    # fields (last_session_id, last_seen_at) rather than overwriting the file.
    state_path = bearings_dir / BEARINGS_DIR_STATE_FILENAME
    try:
        existing: dict[str, object] = (
            dict(bdir_io.read_toml(state_path)) if state_path.exists() else {}
        )
        existing["last_validated"] = last_validated_str
        bdir_io.write_toml(state_path, existing)
    except OSError as exc:
        sys.stderr.write(f"bearings here check: failed to update state.toml: {exc}\n")
        return CLI_EXIT_OPERATION_FAILURE

    sys.stdout.write(f"Revalidated {directory}: {git_summary}.\n")
    sys.stdout.write(f"last_validated = {last_validated_str}\n")
    sys.stdout.write(f"{env_stat}\n")
    return CLI_EXIT_OK


def _parse_git_summary(git_stat: str) -> str:
    """Collapse the full git-status string to a compact branch + state summary.

    ``_git_status`` returns ``"<state>, branch <name>, N changed, S stashes"``
    or ``"not a git repo"``.  This helper returns ``"branch <name>, <state>"``
    or ``"not a git repo"`` for use in the revalidation output line.
    """
    if git_stat == "not a git repo":
        return "not a git repo"
    parts = git_stat.split(", ")
    state = parts[0] if parts else "unknown"
    branch = next(
        (p[len("branch ") :] for p in parts if p.startswith("branch ")),
        "unknown",
    )
    return f"branch {branch}, {state}"


def _resolve_dir(dir_arg: Path | None) -> Path:
    """Return the effective target directory from ``--dir`` or CWD."""
    return dir_arg if dir_arg is not None else Path.cwd()


__all__ = ["build_subparser"]
