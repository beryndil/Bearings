"""Seven-step onboarding ritual — build a structured brief for a
directory the session just landed in.

Steps (from the v0.4 spec):
  1. Identify — find project-root markers, read README head.
  2. Git state — status, stashes, in-progress merge/rebase markers.
  3. Environment validation — Python venv, lockfile freshness, lang
     version pins, DB existence, unapplied migrations.
  4. Related directories — sibling clones with matching remote.
  5. Unfinished work — TODO/FIXME grep, README/CHANGELOG read, plus
     the **naming-inconsistency grep** that addresses the Twrminal
     failure mode.
  6. Tag match — look up Bearings DB rows whose `default_working_dir`
     prefixes this path.
  7. Present — structured `Brief` dataclass the caller renders.

The ritual is pure I/O against the target directory. It does not
write `.bearings/` itself — the caller (CLI or WS-open handler) owns
the confirm-and-write step so a read-only probe stays safe.

Every step returns a small dict-like block so a failure in one step
(e.g. no `git`) degrades gracefully without aborting the rest.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Files that mark "this is a project root" on the walk-up in step 1.
# Order matters for the "primary marker" report — git wins over
# pyproject etc., since a git remote is the strongest identity signal.
_PROJECT_MARKERS: tuple[str, ...] = (
    ".git",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "CLAUDE.md",
    "README.md",
)

_README_HEAD_LINES = 50

# Where sibling clones live. Checked in order; duplicates (same
# resolved remote) are collapsed.
_SIBLING_ROOTS: tuple[Path, ...] = (
    Path.home() / "Projects",
    Path.home() / "code",
    Path.home() / "dev",
    Path.home() / "src",
)

# Grep patterns for step 5. Sourced from the spec.
_UNFINISHED_PATTERNS: tuple[str, ...] = ("TODO", "FIXME", "XXX", "WIP")

# Step-3 sentinel for version-pin files. Presence + content both
# matter — `.python-version` with "3.12" vs the shell `python3`
# reporting `3.11` is a real problem worth flagging.
_VERSION_PIN_FILES: tuple[str, ...] = (
    ".python-version",
    ".nvmrc",
    "rust-toolchain.toml",
    "rust-toolchain",
)


@dataclass(frozen=True)
class Brief:
    """Structured onboarding output. Callers render this however they
    like — CLI prints a text block, the WS handler synthesises an
    assistant message, tests assert against the dict."""

    directory: Path
    primary_marker: str | None
    identity: dict[str, Any] = field(default_factory=dict)
    git: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)
    related: list[dict[str, Any]] = field(default_factory=list)
    unfinished: dict[str, Any] = field(default_factory=dict)
    tag_matches: list[dict[str, Any]] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ───────────── helpers ─────────────


def _run(cmd: list[str], cwd: Path, *, timeout: float = 5.0) -> tuple[int, str, str]:
    """Run `cmd` in `cwd`, return (rc, stdout, stderr). Every failure
    mode is converted to a rc=-1 tuple so callers never have to catch
    exceptions — they just read the tuple.
    """
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return -1, "", f"{type(exc).__name__}: {exc}"
    return proc.returncode, proc.stdout, proc.stderr


def _find_primary_marker(directory: Path) -> str | None:
    """First marker from `_PROJECT_MARKERS` that exists in `directory`
    (not walked up — the target itself). Returns the marker filename
    or `None` if the directory has no recognisable shape.
    """
    for marker in _PROJECT_MARKERS:
        if (directory / marker).exists():
            return marker
    return None


def _head_readme(directory: Path) -> list[str]:
    """First `_README_HEAD_LINES` of `README.md`, empty list on miss."""
    readme = directory / "README.md"
    if not readme.exists():
        return []
    try:
        text = readme.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return text.splitlines()[:_README_HEAD_LINES]


# ───────────── steps ─────────────


def step_identify(directory: Path) -> dict[str, Any]:
    """Step 1 — project markers + README head."""
    primary = _find_primary_marker(directory)
    markers_present = [m for m in _PROJECT_MARKERS if (directory / m).exists()]
    return {
        "primary_marker": primary,
        "markers_present": markers_present,
        "readme_head": _head_readme(directory),
        "name": directory.name,
    }


def step_git_state(directory: Path) -> dict[str, Any]:
    """Step 2 — `git status --porcelain`, stashes, in-progress op
    markers under `.git/`. If the directory isn't a repo, returns
    `{"is_repo": False}` and the rest of the brief carries on.
    """
    git_dir = directory / ".git"
    if not git_dir.exists():
        return {"is_repo": False}
    rc, status, _ = _run(["git", "status", "--porcelain"], directory)
    rc_branch, branch, _ = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], directory)
    rc_stash, stash, _ = _run(["git", "stash", "list"], directory)

    # In-progress markers — presence of these files means a merge /
    # rebase / cherry-pick / bisect is parked. Worth surfacing loudly
    # because dropping into a session mid-rebase is how broken
    # branches happen.
    in_progress: list[str] = []
    for marker in ("MERGE_HEAD", "rebase-apply", "rebase-merge", "CHERRY_PICK_HEAD", "BISECT_LOG"):
        if (git_dir / marker).exists():
            in_progress.append(marker)

    porcelain_lines = [ln for ln in status.splitlines() if ln.strip()]
    return {
        "is_repo": True,
        "branch": branch.strip() if rc_branch == 0 else None,
        "dirty": bool(porcelain_lines),
        "changed_files": len(porcelain_lines),
        "stashes": len([ln for ln in stash.splitlines() if ln.strip()]) if rc_stash == 0 else 0,
        "in_progress": in_progress,
    }


def step_environment(directory: Path) -> dict[str, Any]:
    """Step 3 — venv, lockfile freshness, language pins, DB file.

    The lockfile check uses `uv sync --locked --dry-run` per the spec
    (not `uv pip check` which answers a different question). A
    missing `uv` binary degrades to `lockfile_fresh=None` rather than
    treating a tooling gap as a project defect.
    """
    pins: dict[str, str] = {}
    for pin_file in _VERSION_PIN_FILES:
        path = directory / pin_file
        if path.exists():
            try:
                pins[pin_file] = path.read_text(encoding="utf-8").strip()
            except OSError:
                pins[pin_file] = ""

    venv_path = directory / ".venv"
    has_pyproject = (directory / "pyproject.toml").exists()
    lockfile_fresh: bool | None = None
    notes: list[str] = []
    if has_pyproject and (directory / "uv.lock").exists():
        rc, _, err = _run(["uv", "sync", "--locked", "--dry-run"], directory, timeout=30.0)
        if rc == -1:
            notes.append("uv not available; lockfile freshness unknown")
        else:
            lockfile_fresh = rc == 0
            if rc != 0:
                notes.append(f"uv sync --locked --dry-run exit {rc}: {err.strip()[:200]}")

    return {
        "venv_present": venv_path.exists(),
        "venv_path": str(venv_path) if venv_path.exists() else None,
        "version_pins": pins,
        "lockfile_fresh": lockfile_fresh,
        "notes": notes,
    }


def step_related(directory: Path, remote: str | None) -> list[dict[str, Any]]:
    """Step 4 — sibling clones under the configured roots. A sibling
    is another dir whose git remote resolves to the same URL as the
    target. Slow path (`git -C <dir> config --get remote.origin.url`
    on every candidate) is acceptable because the set is small.
    """
    if remote is None:
        return []
    siblings: list[dict[str, Any]] = []
    seen_paths: set[Path] = {directory.resolve()}
    for root in _SIBLING_ROOTS:
        if not root.exists():
            continue
        try:
            candidates = list(root.iterdir())
        except OSError:
            continue
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in seen_paths or not (candidate / ".git").exists():
                continue
            rc, url, _ = _run(["git", "config", "--get", "remote.origin.url"], candidate)
            if rc == 0 and url.strip() == remote.strip():
                siblings.append({"path": str(candidate), "remote": url.strip()})
                seen_paths.add(resolved)
    return siblings


def git_remote(directory: Path) -> str | None:
    """The target directory's `origin` remote URL, or `None` if the
    directory isn't a repo or has no origin. Exposed (not `_`-
    prefixed) because `manifest.toml` writing needs it too."""
    rc, url, _ = _run(["git", "config", "--get", "remote.origin.url"], directory)
    return url.strip() if rc == 0 and url.strip() else None


def _naming_inconsistencies(directory: Path) -> list[dict[str, str]]:
    """Scan CHANGELOG.md / README.md / CLAUDE.md for pairs of names
    that look like the-same-thing-spelled-differently — the exact
    Twrminal/Bearings failure class.

    v0.6.0 heuristic: pull the project's own name from
    `pyproject.toml` or the directory name, grep the narrative files
    for any alphanumeric identifier that differs from the canonical
    name by edit distance ≤ 2 but isn't a substring relation. Returns
    findings as dicts; the brief renders them as "note, not problem"
    copy.
    """
    canonical = directory.name
    pyproject = directory / "pyproject.toml"
    if pyproject.exists():
        try:
            for line in pyproject.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("name") and "=" in stripped:
                    value = stripped.split("=", 1)[1].strip().strip("\"'")
                    if value:
                        canonical = value
                        break
        except OSError:
            pass

    findings: list[dict[str, str]] = []
    for fname in ("CHANGELOG.md", "README.md", "CLAUDE.md"):
        path = directory / fname
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        words = {w for w in _extract_identifiers(text) if _looks_like_variant(w, canonical)}
        for variant in sorted(words):
            findings.append({"file": fname, "canonical": canonical, "variant": variant})
    return findings


def _extract_identifiers(text: str) -> list[str]:
    """Split `text` into alphabetic identifier-ish tokens. Good enough
    for the naming-variant scan; a full lexer would be overkill."""
    out: list[str] = []
    buf: list[str] = []
    for ch in text:
        if ch.isalpha():
            buf.append(ch)
        else:
            if buf:
                out.append("".join(buf))
                buf = []
    if buf:
        out.append("".join(buf))
    return out


def _looks_like_variant(candidate: str, canonical: str) -> bool:
    """True when `candidate` looks like a misspelling / variant of
    `canonical`. Rules:
      - different from canonical (case-insensitive)
      - not a strict substring / superstring of canonical
      - edit distance ≤ 2
      - length between 4 and 32 to skip trivial tokens
    """
    if len(candidate) < 4 or len(candidate) > 32:
        return False
    lc = candidate.lower()
    cn = canonical.lower()
    if lc == cn:
        return False
    if lc in cn or cn in lc:
        return False
    return _edit_distance(lc, cn) <= 2


def _edit_distance(a: str, b: str) -> int:
    """Classic DP Levenshtein. Fine for the tiny strings here."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[-1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def step_unfinished(directory: Path) -> dict[str, Any]:
    """Step 5 — TODO grep, README/CHANGELOG head, naming scan."""
    rc, grep_out, _ = _run(["git", "grep", "-n", "-E", "|".join(_UNFINISHED_PATTERNS)], directory)
    todo_hits: list[str] = []
    if rc == 0:
        todo_hits = grep_out.splitlines()[:40]  # cap so the brief stays small

    narrative_heads: dict[str, list[str]] = {}
    for fname in ("TODO.md", "CHANGELOG.md", "TESTING_NOTES.md"):
        path = directory / fname
        if path.exists():
            try:
                narrative_heads[fname] = path.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()[:_README_HEAD_LINES]
            except OSError:
                continue

    return {
        "todo_hits": todo_hits,
        "narrative_heads": narrative_heads,
        "naming_findings": _naming_inconsistencies(directory),
    }


def step_tag_match(directory: Path, tag_rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Step 6 — which Bearings tag rows claim this directory.

    Caller passes pre-fetched `tag_rows` (a list of dicts with at
    least `name` and `default_working_dir`) so this module stays
    pure-FS and doesn't pull in `aiosqlite`. The WS-open handler and
    CLI both already have a DB handle; handing the rows in keeps the
    ritual testable without a DB fixture.
    """
    if not tag_rows:
        return []
    dir_str = str(directory.resolve())
    matches: list[dict[str, Any]] = []
    for row in tag_rows:
        default_dir = row.get("default_working_dir") or ""
        if not default_dir:
            continue
        if dir_str.startswith(str(Path(default_dir).resolve())):
            matches.append(dict(row))
    return matches


def run_onboarding(
    directory: Path,
    *,
    tag_rows: list[dict[str, Any]] | None = None,
) -> Brief:
    """Run all 7 steps and assemble a `Brief`. Pure read — does NOT
    write `.bearings/`. The caller confirms and then invokes the
    writers in `io.py` and `pending.py`.
    """
    directory = directory.resolve()
    identity = step_identify(directory)
    git = step_git_state(directory)
    environment = step_environment(directory)
    remote = git_remote(directory) if git.get("is_repo") else None
    related = step_related(directory, remote)
    unfinished = step_unfinished(directory)
    tag_matches = step_tag_match(directory, tag_rows)

    return Brief(
        directory=directory,
        primary_marker=identity["primary_marker"],
        identity=identity,
        git=git,
        environment=environment,
        related=related,
        unfinished=unfinished,
        tag_matches=tag_matches,
    )


def render_brief(brief: Brief) -> str:
    """Human-readable text rendering of a `Brief`. Used by
    `bearings here init` (prints to stdout) and the WS-open handler
    (synthesises the first assistant message in v0.6.2)."""
    lines: list[str] = []
    lines.append(f"Directory: {brief.directory}")
    if brief.primary_marker:
        lines.append(f"Primary marker: {brief.primary_marker}")
    else:
        lines.append("No recognised project markers.")
    git = brief.git
    if git.get("is_repo"):
        state = "dirty" if git.get("dirty") else "clean"
        lines.append(
            f"Git: {state}, branch {git.get('branch') or '(detached)'}, "
            f"{git.get('changed_files', 0)} changed, {git.get('stashes', 0)} stashes"
        )
        if git.get("in_progress"):
            lines.append(f"  In progress: {', '.join(git['in_progress'])}")
    env = brief.environment
    if env.get("lockfile_fresh") is False:
        lines.append("Environment: lockfile stale — run `uv sync`.")
    elif env.get("lockfile_fresh") is True:
        lines.append("Environment: lockfile fresh.")
    for note in env.get("notes", []):
        lines.append(f"  note: {note}")
    if brief.related:
        lines.append(f"Related clones: {len(brief.related)}")
        for sib in brief.related:
            lines.append(f"  - {sib['path']}")
    unfinished = brief.unfinished
    if unfinished.get("todo_hits"):
        lines.append(f"Unfinished markers: {len(unfinished['todo_hits'])} TODO/FIXME/XXX/WIP hits")
    for finding in unfinished.get("naming_findings", []):
        lines.append(
            f"  naming note (NOT a rename in progress): "
            f"'{finding['variant']}' in {finding['file']} near '{finding['canonical']}'"
        )
    if brief.tag_matches:
        tag_names = ", ".join(row.get("name", "?") for row in brief.tag_matches)
        lines.append(f"Tag matches: {tag_names}")
    return "\n".join(lines)


__all__ = [
    "Brief",
    "git_remote",
    "render_brief",
    "run_onboarding",
    "step_environment",
    "step_git_state",
    "step_identify",
    "step_related",
    "step_tag_match",
    "step_unfinished",
]
