"""Bearings CLI entry point.

Skeleton-only for item 0.1 — full ``bearings`` CLI surface (with the ``todo``
subcommand and friends) lands in item 1.7 ("Paired chats + prompt endpoint +
bearings CLI").

Exits 0 with a one-line bootstrap notice so that:

* ``uv run bearings`` does something visible during scaffolding verification,
* the script entry point declared in ``pyproject.toml`` is exercised at test
  time without requiring a full subcommand parser to exist yet.
"""

from __future__ import annotations

import sys

from bearings import __version__

_BOOTSTRAP_MESSAGE = "bearings v{version} (v1 rebuild bootstrap — full CLI lands in item 1.7)\n"


def main(argv: list[str] | None = None) -> int:
    """Print the bootstrap notice and exit 0.

    Args:
        argv: Optional argument vector; reserved for future subcommand
            dispatch. Currently unused.

    Returns:
        Process exit code. Always ``0`` at this stage.
    """
    del argv  # No subcommands wired yet — see module docstring.
    sys.stdout.write(_BOOTSTRAP_MESSAGE.format(version=__version__))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via console_script
    raise SystemExit(main(sys.argv[1:]))
