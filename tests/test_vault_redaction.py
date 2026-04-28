"""Vault redaction-rendering tests.

Per ``docs/behavior/vault.md`` §"Redaction rendering" the server:

* detects credential-shaped tokens adjacent to keywords like
  ``key`` / ``token`` / ``secret`` / ``password``;
* returns the raw body unchanged plus a list of (offset, length,
  pattern) ranges the client masks visually;
* does not transmit modifications back to disk.

These tests pin the regex behavior + offset arithmetic + the
``apply_mask`` helper that produces a server-side rendered string.
"""

from __future__ import annotations

from bearings.agent.vault import apply_mask, detect_redactions
from bearings.config.constants import (
    VAULT_REDACTION_MASK_GLYPH,
    VAULT_REDACTION_MIN_VALUE_CHARS,
)


def test_detect_keyvalue_with_equals_sign() -> None:
    body = "api_key = abcdefghijklmnop"
    redactions = detect_redactions(body)
    assert len(redactions) == 1
    r = redactions[0]
    assert r.pattern == "api_key"
    # value starts after "api_key = " (10 chars)
    assert body[r.offset : r.offset + r.length] == "abcdefghijklmnop"


def test_detect_keyvalue_with_colon() -> None:
    body = "token: longenoughvalue"
    redactions = detect_redactions(body)
    assert len(redactions) == 1
    assert redactions[0].pattern == "token"


def test_detect_keyvalue_with_is_separator() -> None:
    body = "the secret is sup3rs3cr3tval"
    redactions = detect_redactions(body)
    assert len(redactions) == 1
    assert redactions[0].pattern == "secret"


def test_detect_skips_short_value() -> None:
    """Short flag-like values must not be redacted (false-positive guard)."""
    body = "key=on"  # 2-char value, under min
    redactions = detect_redactions(body)
    assert redactions == []


def test_detect_at_minimum_length_boundary() -> None:
    """A value of exactly the minimum length is masked."""
    value = "x" * VAULT_REDACTION_MIN_VALUE_CHARS
    body = f"password={value}"
    redactions = detect_redactions(body)
    assert len(redactions) == 1
    assert redactions[0].length == VAULT_REDACTION_MIN_VALUE_CHARS


def test_detect_is_case_insensitive_on_keyword() -> None:
    body = "API_KEY = abcdefghijklmnop"
    redactions = detect_redactions(body)
    assert len(redactions) == 1
    assert redactions[0].pattern == "api_key"


def test_detect_handles_quoted_value() -> None:
    body = 'token = "longenoughvalue"'
    redactions = detect_redactions(body)
    assert len(redactions) == 1
    # Match should capture the inner value, excluding the quotes.
    assert redactions[0].length == len("longenoughvalue")


def test_detect_multiple_matches_offset_sorted() -> None:
    body = "key=firstvalueXXXX\npassword=secondvalueYYYY\n"
    redactions = detect_redactions(body)
    assert len(redactions) == 2
    assert redactions[0].offset < redactions[1].offset
    assert redactions[0].pattern == "key"
    assert redactions[1].pattern == "password"


def test_detect_no_match_returns_empty() -> None:
    body = "no secrets here, just prose."
    assert detect_redactions(body) == []


def test_detect_does_not_match_unrelated_keyword() -> None:
    body = "username = aliceanderson"
    # "username" is not in VAULT_REDACTION_KEYWORDS — must NOT match.
    assert detect_redactions(body) == []


def test_apply_mask_replaces_value_with_glyph() -> None:
    body = "api_key = abcdefghijklmnop"
    redactions = detect_redactions(body)
    masked = apply_mask(body, redactions)
    assert "abcdefghijklmnop" not in masked
    assert VAULT_REDACTION_MASK_GLYPH in masked
    # Keyword stays visible per vault.md.
    assert "api_key" in masked


def test_apply_mask_preserves_non_redacted_text() -> None:
    body = "before key=longenoughvalue1234 after"
    redactions = detect_redactions(body)
    masked = apply_mask(body, redactions)
    assert masked.startswith("before key=")
    assert masked.endswith(" after")


def test_apply_mask_handles_multiple_ranges_in_reverse() -> None:
    """Ranges process right-to-left so earlier replacements don't shift later offsets."""
    body = "key=firstvalueABCD password=secondvalueEFGH"
    redactions = detect_redactions(body)
    masked = apply_mask(body, redactions)
    assert "firstvalueABCD" not in masked
    assert "secondvalueEFGH" not in masked
    assert masked.count(VAULT_REDACTION_MASK_GLYPH) == 2


def test_apply_mask_no_redactions_returns_body_unchanged() -> None:
    body = "no secrets here"
    assert apply_mask(body, []) == body
