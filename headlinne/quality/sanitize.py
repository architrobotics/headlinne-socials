"""Hard guarantees on generated text.

The model is instructed to avoid em dashes and semicolons, but instructions are
not a guarantee. This module deterministically strips them out (and tidies a few
other model habits) so the rule holds 100% of the time.
"""

from __future__ import annotations

import re

_DASHES = ["\u2014", "\u2013", "\u2015", "\u2012", "--"]  # em, en, horbar, figure, ascii


def _strip_wrapping_quotes(text: str) -> str:
    text = text.strip()
    # Models sometimes wrap the whole post in quotes or code fences.
    text = re.sub(r"^```[a-z]*\n?|\n?```$", "", text).strip()
    if len(text) >= 2 and text[0] in "\"'\u201c\u2018" and text[-1] in "\"'\u201d\u2019":
        inner = text[1:-1]
        if inner.count('"') == 0:  # only unwrap if not breaking real quotes
            text = inner.strip()
    return text


def remove_em_dashes(text: str) -> str:
    # Dash with surrounding spaces acts as a clause break -> comma.
    text = re.sub(r"\s*[\u2014\u2013\u2015\u2012]\s*|\s+--\s+", ", ", text)
    # Any leftover dash variant -> plain hyphen (intra-word use).
    for d in _DASHES:
        text = text.replace(d, "-")
    return text


def remove_semicolons(text: str) -> str:
    # Semicolons become commas to avoid awkward sentence-case fixes.
    text = re.sub(r"\s*;\s*", ", ", text)
    return text


def strip_markdown(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"(?<!\w)`([^`]+)`(?!\w)", r"\1", text)
    return text


def tidy(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\s+([,.!?])", r"\1", text)      # no space before punctuation
    text = re.sub(r"(,\s*){2,}", ", ", text)        # collapse ", ,"
    text = re.sub(r",\s*\.", ".", text)             # ", ." -> "."
    text = re.sub(r"\.{3,}", "...", text)           # keep ellipses sane
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def sanitize(text: str | None) -> str:
    """Full clean-up applied to every generated string before it ships."""
    if not text:
        return ""
    text = _strip_wrapping_quotes(text)
    text = strip_markdown(text)
    text = remove_em_dashes(text)
    text = remove_semicolons(text)
    text = tidy(text)
    return text


def contains_forbidden(text: str) -> list[str]:
    """Report any forbidden characters that somehow survive (for validation)."""
    issues = []
    if any(d in text for d in ("\u2014", "\u2013", "\u2015", "\u2012")):
        issues.append("em/en dash present")
    if ";" in text:
        issues.append("semicolon present")
    return issues
