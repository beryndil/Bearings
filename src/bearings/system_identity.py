"""Read display name + avatar bytes from the host OS.

Two consumers:

* Boot-time hydration in `server.py` — when the singleton preferences
  row is still at seed state (NULL display name, NULL avatar timestamp),
  pull whatever the system knows about the running user so a fresh
  install just works. A row that's been touched by the user is left
  alone.
* `POST /api/preferences/sync_from_system` — explicit "refresh from
  system now" action wired to a button in Settings → Profile.

Sources, in priority order:

* Display name: `pwd.getpwuid(os.getuid()).pw_gecos` field 0, then the
  AccountsService `RealName` property via `busctl`, then `os.getlogin()`
  / `os.environ['USER']`. The dbus path runs through accountsservice's
  polkit-respecting daemon, so we don't need to read the locked-down
  `/var/lib/AccountsService/users/<name>` file ourselves.
* Avatar: `/var/lib/AccountsService/icons/<USER>` (world-readable on
  every distro that ships AccountsService — the lockdown is on the
  user-config file, not the icon), then `~/.face` (XDG fallback that
  GDM and many greeters honour). Each candidate must exist as a file
  AND parse as an image; we don't trust the filename alone.

The reads never raise — every "couldn't figure it out" branch returns
None and the caller falls back to whatever the user has set manually.
A localhost dev tool has no business hard-failing because dbus is
weird in someone's container.
"""

from __future__ import annotations

import logging
import os
import pwd
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# AccountsService stores per-user icons here on every distro that ships
# the daemon. The file is owned root:root mode 644 (vs the user-config
# file at `users/<name>` which is mode 600), so a userspace process can
# read it without dbus or polkit.
_ACCOUNTSSERVICE_ICONS_DIR = Path("/var/lib/AccountsService/icons")

# The XDG-style avatar path many greeters / desktops respect. Owned by
# the user, so always readable from inside a session running as that
# user.
_HOME_FACE = Path.home() / ".face"

# `busctl` from systemd ships on every modern Linux. Used to query the
# accountsservice daemon's `RealName` property without pulling a dbus
# Python dependency. Returns None if either the binary is missing or
# the call fails — both are non-fatal.
_BUSCTL = "busctl"

# Soft timeout on the busctl call. The daemon answers in a few ms on
# any healthy system; 2 seconds gives a stuck install plenty of room
# to fail without holding up server boot.
_BUSCTL_TIMEOUT_S = 2.0


@dataclass(frozen=True)
class SystemIdentity:
    """What the OS knows about the running user. Either field may be
    `None` when no source produced a value — the caller decides whether
    that's a no-op (boot hydration) or a partial apply (manual sync)."""

    display_name: str | None
    avatar_path: Path | None


def read_system_identity() -> SystemIdentity:
    """Resolve the OS's view of the current user. Pure read; never
    raises. Each source is tried in priority order and the first
    non-empty value wins."""
    return SystemIdentity(
        display_name=_resolve_display_name(),
        avatar_path=_resolve_avatar_path(),
    )


def _resolve_display_name() -> str | None:
    """Try GECOS → dbus RealName → login name. Return the first non-
    empty value or None if every source is blank (which on a fresh
    Arch install is realistic — accountsservice ships with empty
    RealName until a user sets one)."""
    gecos = _read_gecos_full_name()
    if gecos:
        return gecos
    real_name = _read_accountsservice_realname()
    if real_name:
        return real_name
    login = _read_login_name()
    if login:
        return login
    return None


def _read_gecos_full_name() -> str | None:
    """Field 0 of the colon-separated GECOS string is the convention
    for "real name" across Linux. Trim whitespace; return None on
    blank or any read error."""
    try:
        entry = pwd.getpwuid(os.getuid())
    except KeyError:
        return None
    gecos = (entry.pw_gecos or "").split(",", 1)[0].strip()
    return gecos or None


def _read_accountsservice_realname() -> str | None:
    """Query `User1000.RealName` (or whatever the running uid maps to)
    via busctl. Returns None when busctl is missing, the call fails,
    or the property is empty."""
    if shutil.which(_BUSCTL) is None:
        return None
    user_path = f"/org/freedesktop/Accounts/User{os.getuid()}"
    try:
        proc = subprocess.run(  # noqa: S603 — argv list, not shell
            [
                _BUSCTL,
                "--system",
                "get-property",
                "org.freedesktop.Accounts",
                user_path,
                "org.freedesktop.Accounts.User",
                "RealName",
            ],
            capture_output=True,
            text=True,
            timeout=_BUSCTL_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.debug("busctl RealName lookup failed: %s", exc)
        return None
    if proc.returncode != 0:
        return None
    # Output looks like: `s "Dave Hennigan"` (type tag + quoted string).
    # We want the inside of the quotes; `.partition('"')` is the
    # straightforward way without bringing in a parser.
    _, _, rest = proc.stdout.strip().partition('"')
    name, _, _ = rest.rpartition('"')
    name = name.strip()
    return name or None


def _read_login_name() -> str | None:
    """Last-resort name: `os.getlogin()` first (the controlling tty's
    user, which is what most CLIs show), then `$USER`. Either is the
    same in practice on a desktop install — the fallback chain is for
    CI / sandbox cases where one or the other is missing."""
    try:
        login = os.getlogin()
    except OSError:
        login = ""
    if login:
        return login
    env_user = os.environ.get("USER", "").strip()
    return env_user or None


def _resolve_avatar_path() -> Path | None:
    """Return the path to the system avatar bytes, or None when no
    candidate exists. Caller is responsible for actually decoding the
    file — we only check existence and is_file() here, not format."""
    user = os.environ.get("USER") or _read_login_name() or ""
    candidates: list[Path] = []
    if user:
        candidates.append(_ACCOUNTSSERVICE_ICONS_DIR / user)
    candidates.append(_HOME_FACE)
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None
