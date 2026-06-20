"""``bearings window`` subcommand — open the Bearings UI in a browser.

Per ``docs/behavior/bearings-cli.md`` §"bearings window" the subcommand:

* Autodetects a Firefox-family or Chromium-family browser.
* Launches the UI URL in a standalone browser window and detaches
  immediately (``Popen`` with ``start_new_session=True``).
* Prints the opened URL + browser path to stderr on success.
* Exits ``1`` when no browser is found (lists tried candidates + paste URL).
* Exits ``2`` when ``--plain`` and ``--profile`` are both supplied.

Per arch §1.1.1 the handler body stays thin: a single call into
:func:`_open_window`.  All browser-detection and process-spawn logic
lives in the domain helper below.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from bearings.config.constants import (
    CLI_EXIT_OK,
    CLI_EXIT_OPERATION_FAILURE,
    CLI_EXIT_USAGE_ERROR,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_WINDOW_FIREFOX_PROFILE_DIR,
    WINDOW_AUTODETECT_CHROMIUM_BROWSERS,
    WINDOW_AUTODETECT_FIREFOX_BROWSERS,
)


def build_subparser(
    parent: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Wire the ``window`` subcommand into ``parent``."""
    p = parent.add_parser(
        "window",
        help="open the Bearings UI in a standalone browser window",
        description=(
            "Open the Bearings web UI in a standalone browser window. "
            "Firefox-family browsers get a Bearings SSB profile "
            "(collapsed tabs/nav/bookmarks via userChrome.css) plus --new-window. "
            "Chromium-family browsers get --app=URL for native chromeless mode. "
            "Use --plain to suppress all Bearings customisation, or --profile "
            "to supply your own browser profile directory."
        ),
    )
    p.add_argument(
        "--host",
        default=None,
        help=f"server host (default: {DEFAULT_HOST})",
    )
    p.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"server port (default: {DEFAULT_PORT})",
    )
    p.add_argument(
        "--browser",
        default=None,
        metavar="PATH",
        help="path or name of browser binary (overrides autodetection)",
    )
    p.add_argument(
        "--plain",
        action="store_true",
        default=False,
        help="open without any Bearings browser customisation",
    )
    p.add_argument(
        "--profile",
        default=None,
        metavar="PATH",
        type=Path,
        help="use a custom browser profile directory instead of the Bearings default",
    )
    p.set_defaults(func=_cmd_window)


def _cmd_window(args: argparse.Namespace) -> int:
    """Handler for ``bearings window``.

    Validates the ``--plain`` / ``--profile`` mutual exclusion, builds the
    UI URL, then delegates to :func:`_open_window`.
    """
    # Manual mutual-exclusion check to produce the exact spec error string.
    if args.plain and args.profile is not None:
        sys.stderr.write("bearings window: --plain and --profile are mutually exclusive.\n")
        return CLI_EXIT_USAGE_ERROR

    from bearings.config.settings import Settings

    settings = Settings()
    host: str = args.host if args.host is not None else settings.host
    port: int = args.port if args.port is not None else settings.port
    url = f"http://{host}:{port}/"

    return _open_window(
        url=url,
        browser_override=args.browser,
        plain=args.plain,
        profile_dir=args.profile,
    )


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------


def _open_window(
    *,
    url: str,
    browser_override: str | None,
    plain: bool,
    profile_dir: Path | None,
) -> int:
    """Locate a browser, build the invocation argv, and spawn the process.

    Returns :data:`~bearings.config.constants.CLI_EXIT_OK` when the process
    is successfully spawned; :data:`~bearings.config.constants.CLI_EXIT_OPERATION_FAILURE`
    when no browser is found.

    The spawned process is detached via ``start_new_session=True`` so
    ``bearings window`` returns immediately once the Popen succeeds.
    """
    browser_path, is_firefox = _find_browser(browser_override)
    if browser_path is None:
        candidates = list(WINDOW_AUTODETECT_FIREFOX_BROWSERS) + list(
            WINDOW_AUTODETECT_CHROMIUM_BROWSERS
        )
        sys.stderr.write(
            f"bearings window: no browser found; tried: {', '.join(candidates)}\n"
            f"  run: bearings window --browser <path-to-browser>\n"
            f"  or paste this URL into any browser: {url}\n"
        )
        return CLI_EXIT_OPERATION_FAILURE

    cmd = _build_browser_cmd(browser_path, url, is_firefox, plain, profile_dir)
    subprocess.Popen(cmd, start_new_session=True)
    sys.stderr.write(f"bearings window: opened {url} via {browser_path}\n")
    return CLI_EXIT_OK


def _find_browser(browser_override: str | None) -> tuple[str | None, bool]:
    """Return ``(resolved_path, is_firefox_family)`` for the chosen browser.

    When *browser_override* is given, it is passed through ``shutil.which``
    (for bare command names) or used verbatim (for absolute paths).  The
    family is inferred from the final path component.

    When no override is given, Firefox-family candidates are tried first;
    Chromium-family candidates are tried if none is found.  Returns
    ``(None, False)`` when no browser is found.
    """
    if browser_override is not None:
        path = shutil.which(browser_override) or browser_override
        name = Path(path).name.lower()
        is_firefox = "firefox" in name
        return path, is_firefox

    for candidate in WINDOW_AUTODETECT_FIREFOX_BROWSERS:
        found = shutil.which(candidate)
        if found is not None:
            return found, True

    for candidate in WINDOW_AUTODETECT_CHROMIUM_BROWSERS:
        found = shutil.which(candidate)
        if found is not None:
            return found, False

    return None, False


def _build_browser_cmd(
    browser_path: str,
    url: str,
    is_firefox: bool,
    plain: bool,
    profile_dir: Path | None,
) -> list[str]:
    """Return the argv list for the browser subprocess.

    * ``--plain`` → bare ``[browser, url]`` with no Bearings customisation.
    * Firefox family → ``--new-window --profile <dir> <url>`` (using the
      Bearings SSB profile dir unless ``--profile`` supplies an override).
    * Chromium family → ``--app=<url>`` for native chromeless mode.
    """
    if plain:
        return [browser_path, url]
    if is_firefox:
        effective_profile = str(
            profile_dir if profile_dir is not None else DEFAULT_WINDOW_FIREFOX_PROFILE_DIR
        )
        return [browser_path, "--new-window", "--profile", effective_profile, url]
    # Chromium family: --app gives the native chromeless "web-app" mode.
    return [browser_path, f"--app={url}"]


__all__ = ["build_subparser"]
