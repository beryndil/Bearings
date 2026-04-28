"""Vault search-surface tests.

Per ``docs/behavior/vault.md`` §"Search semantics" the vault search:

* runs a case-insensitive substring query;
* treats the query as a literal string (no regex);
* returns flat hits with the source doc title / kind, line number,
  and a snippet of the matching line (capped);
* surfaces a ``capped`` flag when the hit count reaches the hard cap;
* returns no hits for a blank query.

These tests exercise the pure :func:`search_entries` function with
synthetic on-disk fixtures so the behavior is reproducible without a
live filesystem layout.
"""

from __future__ import annotations

from pathlib import Path

from bearings.agent.vault import search_entries
from bearings.config.constants import (
    VAULT_KIND_PLAN,
    VAULT_KIND_TODO,
    VAULT_SEARCH_RESULT_CAP,
    VAULT_SEARCH_SNIPPET_MAX_CHARS,
)
from bearings.db.vault import VaultEntry


def _entry(path: Path, *, vault_id: int, kind: str = VAULT_KIND_PLAN) -> VaultEntry:
    return VaultEntry(
        id=vault_id,
        path=str(path),
        slug=path.stem,
        title=path.stem.title(),
        kind=kind,
        mtime=1,
        size=path.stat().st_size,
        last_indexed_at=2,
    )


def test_search_returns_substring_hit_with_line_number(tmp_path: Path) -> None:
    f = tmp_path / "a.md"
    f.write_text("first line\nthe quick fox\nthird line\n", encoding="utf-8")
    result = search_entries([_entry(f, vault_id=1)], "quick")
    assert result.capped is False
    assert len(result.hits) == 1
    hit = result.hits[0]
    assert hit.line_number == 2
    assert "quick fox" in hit.snippet


def test_search_is_case_insensitive(tmp_path: Path) -> None:
    f = tmp_path / "case.md"
    f.write_text("Mixed Case Text\nMore text\n", encoding="utf-8")
    result = search_entries([_entry(f, vault_id=1)], "case")
    assert len(result.hits) == 1
    assert result.hits[0].line_number == 1


def test_search_treats_query_literally(tmp_path: Path) -> None:
    """``foo.bar`` matches the literal substring, not a regex."""
    f = tmp_path / "lit.md"
    f.write_text("see foo.bar here\nfooXbar nope\n", encoding="utf-8")
    result = search_entries([_entry(f, vault_id=1)], "foo.bar")
    assert [h.line_number for h in result.hits] == [1]


def test_search_blank_query_returns_no_hits(tmp_path: Path) -> None:
    f = tmp_path / "x.md"
    f.write_text("any line\n", encoding="utf-8")
    result = search_entries([_entry(f, vault_id=1)], "   ")
    assert result.hits == ()
    assert result.capped is False


def test_search_no_match_returns_empty(tmp_path: Path) -> None:
    f = tmp_path / "n.md"
    f.write_text("lorem ipsum\n", encoding="utf-8")
    result = search_entries([_entry(f, vault_id=1)], "nothing here")
    assert result.hits == ()


def test_search_snippet_capped_with_ellipsis(tmp_path: Path) -> None:
    """Long line snippets trim to ``VAULT_SEARCH_SNIPPET_MAX_CHARS``."""
    f = tmp_path / "long.md"
    long_line = "needle " + ("x" * (VAULT_SEARCH_SNIPPET_MAX_CHARS + 100))
    f.write_text(long_line + "\n", encoding="utf-8")
    result = search_entries([_entry(f, vault_id=1)], "needle")
    assert len(result.hits) == 1
    snippet = result.hits[0].snippet
    assert snippet.endswith("…")
    # snippet should not exceed cap + the ellipsis char
    assert len(snippet) == VAULT_SEARCH_SNIPPET_MAX_CHARS + 1


def test_search_capped_flag_set_when_results_exceed_cap(tmp_path: Path) -> None:
    """A doc with more matches than the cap surfaces capped=True."""
    f = tmp_path / "many.md"
    lines = "\n".join(f"hit line {i}" for i in range(VAULT_SEARCH_RESULT_CAP + 50))
    f.write_text(lines, encoding="utf-8")
    result = search_entries([_entry(f, vault_id=1)], "hit")
    assert result.capped is True
    assert len(result.hits) == VAULT_SEARCH_RESULT_CAP


def test_search_iteration_order_matches_input(tmp_path: Path) -> None:
    """Hits arrive in input-entries order (newest-first by upstream contract)."""
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("token here\n", encoding="utf-8")
    b.write_text("token there\n", encoding="utf-8")
    entries = [_entry(b, vault_id=2), _entry(a, vault_id=1)]
    result = search_entries(entries, "token")
    assert [h.vault_id for h in result.hits] == [2, 1]


def test_search_unreadable_doc_does_not_crash(tmp_path: Path) -> None:
    """Per vault.md §"Failure modes" a single unreadable doc skips silently."""
    real = tmp_path / "real.md"
    real.write_text("token in real\n", encoding="utf-8")
    # Construct an entry pointing at a non-existent path; OSError on
    # read is swallowed.
    ghost = VaultEntry(
        id=99,
        path=str(tmp_path / "missing.md"),
        slug="missing",
        title=None,
        kind=VAULT_KIND_TODO,
        mtime=1,
        size=1,
        last_indexed_at=2,
    )
    result = search_entries([ghost, _entry(real, vault_id=1)], "token")
    assert [h.vault_id for h in result.hits] == [1]


def test_search_special_chars_in_query(tmp_path: Path) -> None:
    """Regex metachars are not interpreted; treated as literal substring."""
    f = tmp_path / "rx.md"
    f.write_text("bracket [match] here\n", encoding="utf-8")
    result = search_entries([_entry(f, vault_id=1)], "[match]")
    assert len(result.hits) == 1
