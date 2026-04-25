"""TODO.md discipline tooling per `~/.claude/specs/todo-discipline-v1.md`.

Public re-exports drive the four ``bearings todo`` subcommands. The
schema, CLI surface, exit codes, and lint rules are locked in the spec
— do not reinvent them here.

``register_parser`` and ``dispatch`` keep argparse wiring local to the
package so ``cli.py`` doesn't grow further past its 400-line target.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from bearings.todo.add import run_add
from bearings.todo.lint import DEFAULT_MAX_AGE_DAYS, run_check
from bearings.todo.open import run_open
from bearings.todo.recent import run_recent

__all__ = ["dispatch", "register_parser", "run_add", "run_check", "run_open", "run_recent"]


def register_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``todo`` subcommand tree on a parent ``add_subparsers``.

    Spec §2.1 mirrors the existing ``here`` / ``pending`` pattern in
    ``cli.py``. Flag surface tracks spec §2.4-2.7 verbatim.
    """
    todo = sub.add_parser("todo", help="TODO.md discipline tooling")
    todo_sub = todo.add_subparsers(dest="todo_command", required=True)
    _add_open_parser(todo_sub)
    _add_check_parser(todo_sub)
    _add_add_parser(todo_sub)
    _add_recent_parser(todo_sub)


def _add_open_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "open",
        help="List Open / In Progress entries from every TODO.md in scope",
    )
    p.add_argument(
        "--status",
        default="Open,In Progress",
        help=(
            "Comma-separated statuses (Open, Blocked, In Progress) or "
            "'any'. Default: 'Open,In Progress'."
        ),
    )
    p.add_argument(
        "--area",
        default="",
        help="Filter to entries whose Area contains this substring (case-insensitive).",
    )
    p.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format. Default: text.",
    )


def _add_check_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("check", help="Lint every TODO.md for format and staleness issues")
    p.add_argument(
        "--max-age-days",
        type=int,
        default=DEFAULT_MAX_AGE_DAYS,
        help=f"Days before an Open entry is flagged stale. Default: {DEFAULT_MAX_AGE_DAYS}.",
    )
    p.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format. Default: text.",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-finding text lines; print only the summary.",
    )


def _add_add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("add", help="Append a properly-formatted stub entry")
    p.add_argument("title", help="Entry title (becomes the H2)")
    p.add_argument(
        "--status",
        default="Open",
        help="Status value (Open, Blocked, In Progress). Default: Open.",
    )
    p.add_argument("--area", default="", help="Free-form area tag (default: empty).")
    p.add_argument("--body", default="", help="Initial body text (default: empty).")
    p.add_argument(
        "--file",
        default=None,
        help="Target TODO.md path. Default: ./TODO.md.",
    )


def _add_recent_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("recent", help="List entries that changed in the last N days")
    p.add_argument(
        "--days",
        type=int,
        default=7,
        help="Window size in days. Default: 7.",
    )
    p.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format. Default: text.",
    )


def dispatch(args: argparse.Namespace) -> int:
    """Route a parsed ``todo <subcommand>`` invocation to its runner."""
    root = Path.cwd().resolve()
    sub = args.todo_command
    if sub == "open":
        return run_open(root, status=args.status, area=args.area, output_format=args.format)
    if sub == "check":
        return run_check(
            root,
            max_age_days=args.max_age_days,
            output_format=args.format,
            quiet=args.quiet,
        )
    if sub == "add":
        target = Path(args.file).resolve() if args.file else None
        return run_add(
            root,
            title=args.title,
            status=args.status,
            area=args.area,
            body=args.body,
            file=target,
        )
    if sub == "recent":
        return run_recent(root, days=args.days, output_format=args.format)
    return 2
