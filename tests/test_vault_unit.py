"""Unit tests for the vault dataclasses + pure helpers.

Covers the agent-layer business logic that does not need a DB:
:class:`VaultEntry` validation, :func:`extract_title`,
:func:`scan_filesystem` (against a ``tmp_path`` with synthesised
plan / todo files), :func:`is_path_in_vault`,
:func:`build_markdown_link`, :class:`SearchHit` invariants.

References:

* ``docs/architecture-v1.md`` §1.1.3 — vault table.
* ``docs/behavior/vault.md`` — entry types, title rule, paste-into-
  message link shape, path-safety contract.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from bearings.agent.vault import (
    SearchHit,
    build_markdown_link,
    extract_title,
    is_path_in_vault,
    scan_filesystem,
)
from bearings.config.constants import KNOWN_VAULT_KINDS, VAULT_KIND_PLAN, VAULT_KIND_TODO
from bearings.config.settings import VaultCfg
from bearings.db.vault import VaultEntry


def _valid_entry_kwargs() -> dict[str, object]:
    return {
        "id": 1,
        "path": "/home/dave/.claude/plans/foo.md",
        "slug": "foo",
        "title": "Foo",
        "kind": VAULT_KIND_PLAN,
        "mtime": 1_700_000_000,
        "size": 1234,
        "last_indexed_at": 1_700_000_001,
    }


# --- VaultEntry validation -------------------------------------------------


def test_vault_entry_constructs_with_valid_fields() -> None:
    entry = VaultEntry(**_valid_entry_kwargs())  # type: ignore[arg-type]
    assert entry.kind == VAULT_KIND_PLAN
    assert entry.title == "Foo"


def test_vault_entry_is_frozen() -> None:
    entry = VaultEntry(**_valid_entry_kwargs())  # type: ignore[arg-type]
    with pytest.raises((AttributeError, TypeError)):
        entry.kind = VAULT_KIND_TODO  # type: ignore[misc]


def test_vault_entry_rejects_empty_path() -> None:
    kwargs = _valid_entry_kwargs()
    kwargs["path"] = ""
    with pytest.raises(ValueError, match="path"):
        VaultEntry(**kwargs)  # type: ignore[arg-type]


def test_vault_entry_rejects_empty_slug() -> None:
    kwargs = _valid_entry_kwargs()
    kwargs["slug"] = ""
    with pytest.raises(ValueError, match="slug"):
        VaultEntry(**kwargs)  # type: ignore[arg-type]


def test_vault_entry_rejects_unknown_kind() -> None:
    kwargs = _valid_entry_kwargs()
    kwargs["kind"] = "snippet"  # not in KNOWN_VAULT_KINDS
    with pytest.raises(ValueError, match="kind"):
        VaultEntry(**kwargs)  # type: ignore[arg-type]


def test_vault_entry_accepts_no_title() -> None:
    kwargs = _valid_entry_kwargs()
    kwargs["title"] = None
    entry = VaultEntry(**kwargs)  # type: ignore[arg-type]
    assert entry.title is None


def test_vault_entry_rejects_negative_mtime() -> None:
    kwargs = _valid_entry_kwargs()
    kwargs["mtime"] = -1
    with pytest.raises(ValueError, match="mtime"):
        VaultEntry(**kwargs)  # type: ignore[arg-type]


def test_vault_entry_rejects_negative_size() -> None:
    kwargs = _valid_entry_kwargs()
    kwargs["size"] = -1
    with pytest.raises(ValueError, match="size"):
        VaultEntry(**kwargs)  # type: ignore[arg-type]


def test_known_vault_kinds_contains_both() -> None:
    assert frozenset({VAULT_KIND_PLAN, VAULT_KIND_TODO}) == KNOWN_VAULT_KINDS


# --- extract_title ---------------------------------------------------------


def test_extract_title_finds_first_h1() -> None:
    assert extract_title("# Title here\n\nbody") == "Title here"


def test_extract_title_ignores_h2() -> None:
    assert extract_title("## not a title\nbody") is None


def test_extract_title_returns_none_for_no_heading() -> None:
    assert extract_title("just body, no heading") is None


def test_extract_title_strips_whitespace() -> None:
    assert extract_title("#   spaced   \nbody") == "spaced"


def test_extract_title_returns_none_for_empty_h1() -> None:
    """``# `` followed by nothing should not yield an empty-string title."""
    assert extract_title("#  \nbody") is None


def test_extract_title_finds_h1_after_other_lines() -> None:
    body = "some preamble\nmore preamble\n# Real title\nthen body"
    assert extract_title(body) == "Real title"


# --- scan_filesystem -------------------------------------------------------


def test_scan_filesystem_finds_plans_in_root(tmp_path: Path) -> None:
    plan_root = tmp_path / "plans"
    plan_root.mkdir()
    (plan_root / "alpha.md").write_text("# Alpha\nbody", encoding="utf-8")
    (plan_root / "beta.md").write_text("# Beta\nbody", encoding="utf-8")
    cfg = VaultCfg(plan_roots=(plan_root,), todo_globs=())
    docs = scan_filesystem(cfg)
    titles = sorted(d.title or "" for d in docs)
    assert titles == ["Alpha", "Beta"]
    assert all(d.kind == VAULT_KIND_PLAN for d in docs)


def test_scan_filesystem_does_not_recurse_into_plan_subdirs(tmp_path: Path) -> None:
    plan_root = tmp_path / "plans"
    archive = plan_root / "archive"
    archive.mkdir(parents=True)
    (plan_root / "live.md").write_text("# Live\n", encoding="utf-8")
    (archive / "old.md").write_text("# Old\n", encoding="utf-8")
    cfg = VaultCfg(plan_roots=(plan_root,), todo_globs=())
    docs = scan_filesystem(cfg)
    assert [d.slug for d in docs] == ["live"]


def test_scan_filesystem_skips_non_markdown(tmp_path: Path) -> None:
    plan_root = tmp_path / "plans"
    plan_root.mkdir()
    (plan_root / "ok.md").write_text("# OK\n", encoding="utf-8")
    (plan_root / "skip.txt").write_text("text", encoding="utf-8")
    cfg = VaultCfg(plan_roots=(plan_root,), todo_globs=())
    docs = scan_filesystem(cfg)
    assert [d.slug for d in docs] == ["ok"]


def test_scan_filesystem_finds_todos_via_glob(tmp_path: Path) -> None:
    proj_a = tmp_path / "projects" / "alpha"
    proj_b = tmp_path / "projects" / "beta"
    proj_a.mkdir(parents=True)
    proj_b.mkdir(parents=True)
    (proj_a / "TODO.md").write_text("# Alpha TODO\n", encoding="utf-8")
    (proj_b / "TODO.md").write_text("body without title", encoding="utf-8")
    glob_pattern = str(tmp_path / "projects" / "**" / "TODO.md")
    cfg = VaultCfg(plan_roots=(), todo_globs=(glob_pattern,))
    docs = scan_filesystem(cfg)
    assert {d.kind for d in docs} == {VAULT_KIND_TODO}
    assert {d.slug for d in docs} == {"TODO"}


def test_scan_filesystem_silently_drops_missing_root(tmp_path: Path) -> None:
    """Per vault.md §"Failure modes" — missing plan roots are silently dropped."""
    real = tmp_path / "real"
    real.mkdir()
    (real / "ok.md").write_text("# Real\n", encoding="utf-8")
    missing = tmp_path / "missing"  # never created
    cfg = VaultCfg(plan_roots=(real, missing), todo_globs=())
    docs = scan_filesystem(cfg)
    assert [d.slug for d in docs] == ["ok"]


def test_scan_filesystem_plans_win_over_todos_on_collision(tmp_path: Path) -> None:
    """A path in both buckets resolves as ``plan``."""
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "TODO.md").write_text("# Shared\n", encoding="utf-8")
    cfg = VaultCfg(
        plan_roots=(shared,),
        todo_globs=(str(shared / "TODO.md"),),
    )
    docs = scan_filesystem(cfg)
    assert len(docs) == 1
    assert docs[0].kind == VAULT_KIND_PLAN


def test_scan_filesystem_resolves_symlinks(tmp_path: Path) -> None:
    """Per vault.md the index reports resolved paths."""
    real_root = tmp_path / "real_plans"
    real_root.mkdir()
    target = real_root / "doc.md"
    target.write_text("# T\n", encoding="utf-8")
    link_root = tmp_path / "link_plans"
    os.symlink(real_root, link_root)
    cfg = VaultCfg(plan_roots=(link_root,), todo_globs=())
    docs = scan_filesystem(cfg)
    assert len(docs) == 1
    assert docs[0].path == str(target.resolve(strict=True))


# --- is_path_in_vault ------------------------------------------------------


def test_is_path_in_vault_accepts_known_path(tmp_path: Path) -> None:
    target = tmp_path / "ok.md"
    target.write_text("# x\n", encoding="utf-8")
    entries = [
        VaultEntry(
            id=1,
            path=str(target.resolve(strict=True)),
            slug="ok",
            title="x",
            kind=VAULT_KIND_PLAN,
            mtime=1,
            size=4,
            last_indexed_at=2,
        )
    ]
    assert is_path_in_vault(target, entries) is True


def test_is_path_in_vault_rejects_outside_path(tmp_path: Path) -> None:
    target = tmp_path / "ok.md"
    target.write_text("# x\n", encoding="utf-8")
    other = tmp_path / "outside.md"
    other.write_text("# y\n", encoding="utf-8")
    entries = [
        VaultEntry(
            id=1,
            path=str(target.resolve(strict=True)),
            slug="ok",
            title="x",
            kind=VAULT_KIND_PLAN,
            mtime=1,
            size=4,
            last_indexed_at=2,
        )
    ]
    assert is_path_in_vault(other, entries) is False


def test_is_path_in_vault_resolves_symlinks_before_check(tmp_path: Path) -> None:
    """Per vault.md §"Failure modes": symlink trick into the vault must resolve."""
    real = tmp_path / "real.md"
    real.write_text("# r\n", encoding="utf-8")
    link = tmp_path / "link.md"
    os.symlink(real, link)
    entries = [
        VaultEntry(
            id=1,
            path=str(real.resolve(strict=True)),
            slug="real",
            title="r",
            kind=VAULT_KIND_PLAN,
            mtime=1,
            size=4,
            last_indexed_at=2,
        )
    ]
    # Asking for the link path should resolve to ``real`` and pass.
    assert is_path_in_vault(link, entries) is True


def test_is_path_in_vault_returns_false_for_nonexistent(tmp_path: Path) -> None:
    entries: list[VaultEntry] = []
    assert is_path_in_vault(tmp_path / "missing.md", entries) is False


# --- build_markdown_link ---------------------------------------------------


def test_build_markdown_link_uses_title_when_set() -> None:
    entry = VaultEntry(
        id=1,
        path="/abs/foo.md",
        slug="foo",
        title="Foo Plan",
        kind=VAULT_KIND_PLAN,
        mtime=1,
        size=10,
        last_indexed_at=2,
    )
    assert build_markdown_link(entry) == "[Foo Plan](file:///abs/foo.md)"


def test_build_markdown_link_falls_back_to_slug_when_title_none() -> None:
    entry = VaultEntry(
        id=1,
        path="/abs/foo.md",
        slug="foo",
        title=None,
        kind=VAULT_KIND_PLAN,
        mtime=1,
        size=10,
        last_indexed_at=2,
    )
    assert build_markdown_link(entry) == "[foo](file:///abs/foo.md)"


# --- SearchHit invariants --------------------------------------------------


def test_search_hit_rejects_zero_line_number() -> None:
    with pytest.raises(ValueError, match="line_number"):
        SearchHit(
            vault_id=1,
            path="/abs/x.md",
            title=None,
            kind=VAULT_KIND_PLAN,
            line_number=0,
            snippet="x",
        )
