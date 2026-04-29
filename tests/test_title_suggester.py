"""Tests for `bearings.agent.title_suggester` — auto-suggest-titles
plan (`~/.claude/plans/auto-suggesting-titles.md`).

Pure-helper coverage: parser, validator, and the `suggest_titles()`
two-attempt retry loop driven by the `query_fn` test seam. The
route-level / config-gate behaviors are covered in
`test_routes_suggest_title.py`.
"""

from __future__ import annotations

import pytest

from bearings.agent.title_suggester import (
    _clean_title,
    _extract_json_block,
    _validate_titles,
    suggest_titles,
)


def test_clean_title_strips_whitespace_and_quotes() -> None:
    assert _clean_title('  "Hello world"  ') == "Hello world"
    assert _clean_title("'single quoted'") == "single quoted"
    assert _clean_title("multi   space   collapse") == "multi space collapse"


def test_clean_title_clamps_to_60_chars() -> None:
    raw = "x" * 100
    cleaned = _clean_title(raw)
    assert cleaned is not None
    assert len(cleaned) == 60


def test_clean_title_returns_none_for_non_strings() -> None:
    assert _clean_title(123) is None
    assert _clean_title(None) is None
    assert _clean_title("") is None
    assert _clean_title("   ") is None


def test_extract_json_block_skips_preface() -> None:
    text = 'Here you go:\n```json\n{"titles": ["a", "b", "c"]}\n```'
    parsed = _extract_json_block(text)
    assert parsed == {"titles": ["a", "b", "c"]}


def test_extract_json_block_returns_none_on_no_brace() -> None:
    assert _extract_json_block("no json here") is None


def test_validate_titles_happy_path() -> None:
    parsed = {"titles": ["Narrow", "Medium", "Wide"]}
    assert _validate_titles(parsed) == ["Narrow", "Medium", "Wide"]


def test_validate_titles_rejects_short_list() -> None:
    assert _validate_titles({"titles": ["only one"]}) is None
    assert _validate_titles({"titles": []}) is None


def test_validate_titles_clamps_long_list_to_three() -> None:
    parsed = {"titles": ["a", "b", "c", "d", "e"]}
    assert _validate_titles(parsed) == ["a", "b", "c"]


def test_validate_titles_skips_unusable_entries() -> None:
    """Three usable strings are needed; non-strings and empties are
    skipped. With only two usable entries here the validator returns
    None so the caller can fall through to its retry."""
    parsed = {"titles": [None, "good one", "", "good two"]}
    assert _validate_titles(parsed) is None


def test_validate_titles_rejects_missing_key() -> None:
    assert _validate_titles({}) is None
    assert _validate_titles({"titles": "not a list"}) is None


@pytest.mark.asyncio
async def test_suggest_titles_happy_path() -> None:
    async def fake_query(_messages: list[dict[str, object]]) -> str:
        return '{"titles": ["Narrow take", "Medium take", "Wide take"]}'

    titles, notes = await suggest_titles(
        [{"id": "m1", "role": "user", "content": "hi"}],
        model="claude-haiku-4-5",
        query_fn=fake_query,
    )
    assert titles == ["Narrow take", "Medium take", "Wide take"]
    assert notes == ""


@pytest.mark.asyncio
async def test_suggest_titles_retries_on_parse_failure() -> None:
    calls: list[int] = []

    async def flaky(_messages: list[dict[str, object]]) -> str:
        calls.append(1)
        if len(calls) == 1:
            return "totally not json"
        return '{"titles": ["a", "b", "c"]}'

    titles, notes = await suggest_titles(
        [{"id": "m1", "role": "user", "content": "hi"}],
        model="claude-haiku-4-5",
        query_fn=flaky,
    )
    assert titles == ["a", "b", "c"]
    assert notes == ""
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_suggest_titles_returns_none_after_two_failures() -> None:
    async def always_bad(_messages: list[dict[str, object]]) -> str:
        return "no json"

    titles, notes = await suggest_titles(
        [{"id": "m1", "role": "user", "content": "hi"}],
        model="claude-haiku-4-5",
        query_fn=always_bad,
    )
    assert titles is None
    assert "unparseable" in notes.lower()


@pytest.mark.asyncio
async def test_suggest_titles_returns_none_when_query_raises() -> None:
    async def boom(_messages: list[dict[str, object]]) -> str:
        raise RuntimeError("transient SDK failure")

    titles, notes = await suggest_titles(
        [{"id": "m1", "role": "user", "content": "hi"}],
        model="claude-haiku-4-5",
        query_fn=boom,
    )
    assert titles is None
    assert "transient" in notes.lower() or "failed" in notes.lower()
