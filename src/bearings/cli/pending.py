"""``bearings pending`` subcommand surface.

Per ``docs/behavior/bearings-cli.md`` §"bearings pending" the user sees
three sub-subcommands:

* ``add`` — write (or update) the named row in ``.bearings/pending.toml``
  and print ``Pending: <name> (started <iso8601>)``.
* ``resolve`` — remove the named row and print ``Resolved: <name>``;
  unknown name → stderr + exit 1.
* ``list`` — print all ops oldest-first; empty case prints
  ``(no pending operations)``.

Per arch §1.1.1 the subcommand body stays thin: parsing per-sub-subcommand
args, calling into :mod:`bearings.bearings_dir.pending`, formatting output.
No business logic.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from bearings.bearings_dir import pending as bdir_pending
from bearings.config.constants import (
    CLI_EXIT_OK,
    CLI_EXIT_OPERATION_FAILURE,
)


def build_subparser(parent: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Wire the three ``pending`` sub-subcommands into *parent*.

    The parent is the root ``bearings`` parser's subparsers action;
    this function adds ``pending`` and its own internal subparsers.
    """
    pending = parent.add_parser(
        "pending",
        help="manage in-flight operations in .bearings/pending.toml",
        description=(
            "Add, resolve, or list pending operations tracked in "
            "``.bearings/pending.toml`` per docs/behavior/bearings-cli.md."
        ),
    )
    pending_sub = pending.add_subparsers(
        dest="pending_subcommand",
        metavar="<pending-subcommand>",
        required=True,
    )
    _build_add_parser(pending_sub)
    _build_resolve_parser(pending_sub)
    _build_list_parser(pending_sub)
    pending.set_defaults(func=_dispatch_unknown)


def _build_add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """``bearings pending add`` — write a new row to pending.toml."""
    parser = sub.add_parser(
        "add",
        help="add a pending operation to .bearings/pending.toml",
    )
    parser.add_argument("name", help="unique name for the pending operation")
    parser.add_argument(
        "--description",
        default=None,
        help="human-readable description of the operation",
    )
    parser.add_argument(
        "--command",
        default=None,
        help="optional command string associated with the operation",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="project root containing .bearings/ (default: CWD)",
    )
    parser.set_defaults(func=_run_add)


def _build_resolve_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """``bearings pending resolve`` — remove the named row."""
    parser = sub.add_parser(
        "resolve",
        help="mark a pending operation as resolved",
    )
    parser.add_argument("name", help="name of the pending operation to resolve")
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="project root containing .bearings/ (default: CWD)",
    )
    parser.set_defaults(func=_run_resolve)


def _build_list_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """``bearings pending list`` — print all ops oldest-first."""
    parser = sub.add_parser(
        "list",
        help="list all pending operations oldest-first",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="project root containing .bearings/ (default: CWD)",
    )
    parser.set_defaults(func=_run_list)


# --------------------------------------------------------------------------
# Sub-subcommand bodies
# --------------------------------------------------------------------------


def _run_add(args: argparse.Namespace) -> int:
    """Implement ``bearings pending add``.

    Writes (or updates) the named row in ``.bearings/pending.toml`` and
    prints ``Pending: <name> (started <iso8601>)``.  Returns exit 0.
    """
    directory = _resolve_dir(args.dir)
    started_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    path, ops = bdir_pending.load_ops(directory)
    op: dict[str, str] = {"started_at": started_at}
    if args.description is not None:
        op["description"] = args.description
    if args.command is not None:
        op["command"] = args.command
    ops[args.name] = op
    bdir_pending.save_ops(path, ops)
    sys.stdout.write(f"Pending: {args.name} (started {started_at})\n")
    return CLI_EXIT_OK


def _run_resolve(args: argparse.Namespace) -> int:
    """Implement ``bearings pending resolve``.

    Removes the named row from ``.bearings/pending.toml`` and prints
    ``Resolved: <name>``.  On an unknown name prints to stderr and
    returns exit 1.
    """
    directory = _resolve_dir(args.dir)
    try:
        bdir_pending.remove_op(directory, args.name)
    except KeyError:
        sys.stderr.write(f"No pending op named '{args.name}'.\n")
        return CLI_EXIT_OPERATION_FAILURE
    sys.stdout.write(f"Resolved: {args.name}\n")
    return CLI_EXIT_OK


def _run_list(args: argparse.Namespace) -> int:
    """Implement ``bearings pending list``.

    Prints all pending operations oldest-first formatted as
    ``<iso8601>  <name> — <description>``, or ``(no pending operations)``
    when the ops table is empty.  Returns exit 0.
    """
    directory = _resolve_dir(args.dir)
    _, ops = bdir_pending.load_ops(directory)
    if not ops:
        sys.stdout.write("(no pending operations)\n")
        return CLI_EXIT_OK
    # Sort oldest-first by started_at; ISO8601 strings sort lexicographically.
    sorted_names = sorted(
        ops.keys(),
        key=lambda n: str(ops[n].get("started_at", "")),
    )
    for name in sorted_names:
        op = ops[name]
        started = str(op.get("started_at", ""))
        description = str(op.get("description", "")) if op.get("description") else None
        if description:
            sys.stdout.write(f"{started}  {name} — {description}\n")
        else:
            sys.stdout.write(f"{started}  {name}\n")
    return CLI_EXIT_OK


def _dispatch_unknown(args: argparse.Namespace) -> int:
    """Fallback when ``pending`` is invoked without a sub-subcommand.

    argparse's ``required=True`` on the subparsers prints the usage
    block to stderr automatically; this body should never be reached
    in production.
    """
    del args
    sys.stderr.write("bearings pending: missing sub-subcommand\n")
    return CLI_EXIT_OPERATION_FAILURE


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _resolve_dir(dir_arg: Path | None) -> Path:
    """Return the effective project root from ``--dir`` or CWD."""
    return dir_arg if dir_arg is not None else Path.cwd()


__all__ = ["build_subparser"]
