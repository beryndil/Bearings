from __future__ import annotations

from pathlib import Path

from bearings.api import commands_scan


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_parse_description_no_frontmatter() -> None:
    assert commands_scan._parse_description("# Title\n\nbody") == ""


def test_parse_description_basic() -> None:
    text = "---\ndescription: Hello world\n---\n\nbody"
    assert commands_scan._parse_description(text) == "Hello world"


def test_parse_description_quoted() -> None:
    text = '---\ndescription: "quoted value"\nother: x\n---\n\nbody'
    assert commands_scan._parse_description(text) == "quoted value"


def test_parse_description_missing_key() -> None:
    text = "---\nname: foo\nallowed-tools: [Read]\n---\n\nbody"
    assert commands_scan._parse_description(text) == ""


def test_parse_description_malformed_frontmatter_falls_through() -> None:
    # No closing `---`; regex won't match — treat as bodyless.
    text = "---\ndescription: dangling\n\nbody"
    assert commands_scan._parse_description(text) == ""


def test_collect_user_commands_nested_dirs(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write(home / ".claude/commands/simple.md", "body")
    _write(home / ".claude/commands/fad/ship.md", "---\ndescription: Ship it\n---\nbody")
    _write(home / ".claude/commands/fad/help.md", "body")

    entries = commands_scan.collect(home=home, project_cwd=None)
    slugs = [e.slug for e in entries]
    assert slugs == ["fad:help", "fad:ship", "simple"]
    ship = next(e for e in entries if e.slug == "fad:ship")
    assert ship.description == "Ship it"
    assert ship.scope == "user"
    assert ship.kind == "command"


def test_collect_user_skills(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write(home / ".claude/skills/review/SKILL.md", "---\ndescription: Review code\n---\nbody")
    _write(home / ".claude/skills/no-frontmatter/SKILL.md", "body")
    # A bare dir without SKILL.md must be ignored.
    (home / ".claude/skills/empty").mkdir(parents=True)

    entries = commands_scan.collect(home=home, project_cwd=None)
    slugs = [e.slug for e in entries]
    assert slugs == ["no-frontmatter", "review"]
    review = next(e for e in entries if e.slug == "review")
    assert review.kind == "skill"
    assert review.scope == "user"
    assert review.description == "Review code"


def test_collect_plugin_entries_get_namespace_prefix(tmp_path: Path) -> None:
    home = tmp_path / "home"
    plugin = home / ".claude/plugins/marketplaces/mkt/plugins/commit-commands"
    _write(plugin / "commands/commit.md", "---\ndescription: Make a commit\n---\nbody")
    _write(plugin / "skills/helper/SKILL.md", "---\ndescription: Help\n---\nbody")

    entries = commands_scan.collect(home=home, project_cwd=None)
    slugs = {e.slug: e for e in entries}
    assert "commit-commands:commit" in slugs
    assert slugs["commit-commands:commit"].scope == "plugin"
    assert slugs["commit-commands:commit"].description == "Make a commit"
    assert "commit-commands:helper" in slugs
    assert slugs["commit-commands:helper"].kind == "skill"


def test_collect_project_scope_takes_precedence_over_user(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    _write(home / ".claude/commands/shared.md", "---\ndescription: from user\n---\n")
    _write(project / ".claude/commands/shared.md", "---\ndescription: from project\n---\n")

    entries = commands_scan.collect(home=home, project_cwd=project)
    matches = [e for e in entries if e.slug == "shared"]
    assert len(matches) == 1
    assert matches[0].scope == "project"
    assert matches[0].description == "from project"


def test_collect_empty_when_no_dotclaude(tmp_path: Path) -> None:
    home = tmp_path / "empty-home"
    home.mkdir()
    assert commands_scan.collect(home=home, project_cwd=None) == []


def test_collect_results_are_sorted_case_insensitive(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write(home / ".claude/commands/Zeta.md", "body")
    _write(home / ".claude/commands/alpha.md", "body")
    _write(home / ".claude/commands/Beta.md", "body")
    entries = commands_scan.collect(home=home, project_cwd=None)
    assert [e.slug for e in entries] == ["alpha", "Beta", "Zeta"]


# ---- scope config (2026-04-21 security audit §5) --------------------


def _populate_all_scopes(tmp_path: Path) -> tuple[Path, Path]:
    """Lay down one command at each scope: project `proj-cmd`, user
    `user-cmd`, plugin `plug:cmd`. Returns (home, project)."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    _write(project / ".claude/commands/proj-cmd.md", "body")
    _write(home / ".claude/commands/user-cmd.md", "body")
    plugin = home / ".claude/plugins/marketplaces/mkt/plugins/plug"
    _write(plugin / "commands/cmd.md", "body")
    return home, project


def test_collect_scope_all_is_default_and_walks_every_source(tmp_path: Path) -> None:
    home, project = _populate_all_scopes(tmp_path)
    entries = commands_scan.collect(home=home, project_cwd=project)
    slugs = {e.slug for e in entries}
    assert {"proj-cmd", "user-cmd", "plug:cmd"} <= slugs


def test_collect_scope_user_skips_plugins(tmp_path: Path) -> None:
    home, project = _populate_all_scopes(tmp_path)
    entries = commands_scan.collect(home=home, project_cwd=project, scope="user")
    slugs = {e.slug for e in entries}
    assert "proj-cmd" in slugs
    assert "user-cmd" in slugs
    assert "plug:cmd" not in slugs


def test_collect_scope_project_skips_user_and_plugins(tmp_path: Path) -> None:
    home, project = _populate_all_scopes(tmp_path)
    entries = commands_scan.collect(home=home, project_cwd=project, scope="project")
    slugs = {e.slug for e in entries}
    assert slugs == {"proj-cmd"}
