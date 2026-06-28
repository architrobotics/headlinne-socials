"""The brief forbids em dashes and semicolons. These tests prove the sanitizer
removes them no matter how the model writes, and tidies common model habits."""

from __future__ import annotations

from headlinne.quality.sanitize import (
    contains_forbidden,
    remove_em_dashes,
    remove_semicolons,
    sanitize,
    strip_markdown,
)


def test_em_dash_becomes_comma():
    out = sanitize("Markets rose today \u2014 investors were relieved.")
    assert "\u2014" not in out
    assert "," in out
    assert contains_forbidden(out) == []


def test_en_dash_removed():
    out = sanitize("The deal \u2013 worth billions \u2013 closed fast.")
    assert "\u2013" not in out
    assert contains_forbidden(out) == []


def test_double_hyphen_treated_as_dash():
    out = remove_em_dashes("It happened -- and quickly.")
    assert "--" not in out


def test_intraword_hyphen_survives_as_plain_hyphen():
    # A real hyphenated word must not be mangled into a comma.
    out = sanitize("This is a well-known story.")
    assert "well-known" in out


def test_semicolons_become_commas():
    out = remove_semicolons("One thing; another thing; a third.")
    assert ";" not in out
    assert sanitize("a; b") and ";" not in sanitize("a; b")


def test_contains_forbidden_flags_both():
    issues = contains_forbidden("bad \u2014 and worse;")
    assert any("dash" in i for i in issues)
    assert any("semicolon" in i for i in issues)


def test_markdown_is_stripped():
    out = strip_markdown("This is **bold** and *italic* and `code`.")
    assert "*" not in out
    assert "`" not in out
    assert "bold" in out and "italic" in out and "code" in out


def test_wrapping_quotes_removed():
    out = sanitize('"This whole post was wrapped in quotes."')
    assert not out.startswith('"')
    assert not out.endswith('"')


def test_code_fence_removed():
    out = sanitize("```\njust text\n```")
    assert "`" not in out
    assert "just text" in out


def test_none_and_empty_are_safe():
    assert sanitize(None) == ""
    assert sanitize("") == ""


def test_extra_spaces_and_space_before_punct_tidied():
    out = sanitize("Hello   world .  Nice !")
    assert "  " not in out
    assert " ." not in out
    assert " !" not in out
