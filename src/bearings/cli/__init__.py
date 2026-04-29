"""Bearings CLI — entry point package.

Per ``docs/architecture-v1.md`` §1.1.1 the CLI is the top of the
import-graph stack (``cli > web > agent > db``); per
``docs/behavior/bearings-cli.md`` it exposes the ``bearings``
console-script with subcommands the user types from a shell. The
``[project.scripts]`` declaration in ``pyproject.toml`` resolves
``bearings`` to :func:`main` re-exported from this package's
``__init__`` (preserves backward compatibility with the item-0.1
console-script wiring).

Item 1.7 lays:

* :mod:`bearings.cli.app` — argparse root + dispatch + global flags.
* :mod:`bearings.cli.todo` — ``bearings todo`` subcommand surface.
* :mod:`bearings.cli._todo_io` — TODO.md walker + parser helpers.

Stubs for ``serve`` / ``init`` / ``window`` / ``send`` / ``here`` /
``pending`` / ``gc`` are deferred to subsequent items per behavior
doc + arch §1.1.1; the ``todo`` subcommand is the master-item
done-when call-out.
"""

from __future__ import annotations

from bearings.cli.app import main

__all__ = ["main"]
