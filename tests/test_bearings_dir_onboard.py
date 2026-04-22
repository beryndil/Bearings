"""Tests for the 7-step onboarding ritual + `bearings check` /
`init` write path.

Covers the Twrminal naming-inconsistency case explicitly: a
`CHANGELOG.md` mentioning a near-variant of the project name must
surface as a note, not as a rename-in-progress defect.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from bearings.bearings_dir.check import manifest_exists, run_check
from bearings.bearings_dir.init_dir import init_directory
from bearings.bearings_dir.io import (
    MANIFEST_FILE,
    PENDING_FILE,
    STATE_FILE,
    bearings_path,
    read_toml_model,
)
from bearings.bearings_dir.onboard import (
    render_brief,
    run_onboarding,
    step_environment,
    step_git_state,
    step_identify,
    step_tag_match,
    step_unfinished,
)
from bearings.bearings_dir.schema import Manifest, Pending, State


def _init_git_repo(path: Path) -> None:
    """Make `path` a minimal git repo with one commit so step 2 has
    something to report."""
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "README.md").write_text("# testproj\n\nSample.\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


def test_step_identify_reports_primary_marker(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("line1\nline2\n", encoding="utf-8")
    result = step_identify(tmp_path)
    # .git wins when present; here it's absent, so pyproject.toml is primary.
    assert result["primary_marker"] == "pyproject.toml"
    assert "README.md" in result["markers_present"]
    assert result["readme_head"] == ["line1", "line2"]


def test_step_git_state_on_repo(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "new.txt").write_text("dirty\n", encoding="utf-8")
    state = step_git_state(tmp_path)
    assert state["is_repo"] is True
    assert state["branch"] == "main"
    assert state["dirty"] is True
    assert state["changed_files"] >= 1
    assert state["in_progress"] == []


def test_step_git_state_outside_repo(tmp_path: Path) -> None:
    assert step_git_state(tmp_path) == {"is_repo": False}


def test_step_environment_notes_missing_lockfile_gracefully(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    env = step_environment(tmp_path)
    # No uv.lock → we don't run uv at all → lockfile_fresh stays None.
    assert env["lockfile_fresh"] is None
    assert env["venv_present"] is False


def test_naming_inconsistency_is_flagged_not_errored(tmp_path: Path) -> None:
    """The Twrminal failure mode: a CHANGELOG mentioning 'Twrminal'
    near project name 'Terminal' is surfaced as a note, not a crash
    or a defect marker."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'Terminal'\n", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(
        "# changelog\n\nv0.1 — forked from Twrminal.\n",
        encoding="utf-8",
    )
    unfinished = step_unfinished(tmp_path)
    findings = unfinished["naming_findings"]
    variants = {f["variant"].lower() for f in findings}
    assert "twrminal" in variants
    for finding in findings:
        assert finding["canonical"].lower() == "terminal"
        assert finding["file"] == "CHANGELOG.md"


def test_step_tag_match_prefix(tmp_path: Path) -> None:
    """Tag rows whose `default_working_dir` prefixes the target
    directory should match; unrelated rows should not."""
    tag_rows = [
        {"name": "proj", "default_working_dir": str(tmp_path)},
        {"name": "other", "default_working_dir": "/nowhere/else"},
    ]
    matches = step_tag_match(tmp_path, tag_rows)
    assert len(matches) == 1
    assert matches[0]["name"] == "proj"


def test_run_onboarding_returns_full_brief(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'testproj'\n", encoding="utf-8")
    brief = run_onboarding(tmp_path)
    assert brief.directory == tmp_path.resolve()
    assert brief.git["is_repo"] is True
    assert brief.primary_marker == ".git"
    text = render_brief(brief)
    assert "Directory:" in text
    assert "Git:" in text


def test_init_directory_writes_manifest_state_pending(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'testproj'\n", encoding="utf-8")
    brief, root = init_directory(tmp_path)
    assert root == bearings_path(tmp_path.resolve())
    manifest = read_toml_model(root / MANIFEST_FILE, Manifest)
    state = read_toml_model(root / STATE_FILE, State)
    pending = read_toml_model(root / PENDING_FILE, Pending)
    assert manifest is not None and manifest.name == tmp_path.name
    assert state is not None and state.branch == "main"
    assert pending is not None and pending.operations == []
    assert brief.git["is_repo"] is True


def test_run_check_requires_prior_init(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_check(tmp_path)


def test_run_check_updates_last_validated(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    init_directory(tmp_path)
    original = read_toml_model(bearings_path(tmp_path.resolve()) / STATE_FILE, State)
    assert original is not None
    refreshed = run_check(tmp_path)
    assert refreshed.environment.last_validated >= original.environment.last_validated


def test_manifest_exists_toggle(tmp_path: Path) -> None:
    assert manifest_exists(tmp_path) is False
    _init_git_repo(tmp_path)
    init_directory(tmp_path)
    assert manifest_exists(tmp_path) is True
