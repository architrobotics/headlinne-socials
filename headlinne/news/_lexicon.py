"""Boundary-anchored term matching, shared by news.interest and news.quality.

Both modules are lists of editorial judgement written down as vocabulary, and
both were originally matched with a raw `term in text` substring test. Measured
against real published headlines that produced:

    "Samsung Electronics ..."   matched "sun"        -> scored as universal
    "... last twice as long"    matched "ice"        -> scored as concrete
    "... WARN notice says"      matched "ice"        -> scored as concrete
    "Researchers always to ..." matched "ways to"    -> rejected as a listicle

and, in the other direction, `discovered` failed to match "Scientists
**discover** why ...", scoring a real finding at zero novelty.

So terms match on word boundaries here, with two deliberate escape hatches:

  * a trailing `*` marks a stem - `discover*` matches discovers, discovered and
    discovery, but `star` still will not match "start"
  * boundaries are only applied at ends that are actually word characters, so
    `watch:`, `review:` and `% off` match the way they read

Longest term first, so a specific entry is never shadowed by a prefix of it
(`first-ever` would otherwise always lose to `first`).
"""

from __future__ import annotations

import re

_WORDISH = re.compile(r"\w")


def compile_terms(terms: tuple[str, ...]) -> re.Pattern[str]:
    """One alternation for a whole lexicon, anchored where anchoring is valid."""
    parts: list[str] = []
    for term in sorted(terms, key=len, reverse=True):
        stem = term.endswith("*")
        body = term[:-1] if stem else term
        if not body:
            continue
        # A leading \b only means anything if the term starts with a word
        # character. "% off" starts with punctuation, and \b% would demand a
        # word character immediately before the percent sign.
        head = r"\b" if _WORDISH.match(body[0]) else ""
        if stem:
            tail = r"\w*"
        elif _WORDISH.match(body[-1]):
            tail = r"\b"
        else:
            # "watch:" ends in a colon. \b after it would require a word
            # character next, and what actually follows is a space - which is
            # how "Watch: Fed Chairman testifies" escaped the housekeeping rule.
            tail = ""
        parts.append(f"{head}{re.escape(body)}{tail}")
    return re.compile("(?:" + "|".join(parts) + ")", re.I)


def distinct_hits(text: str, pattern: re.Pattern[str]) -> int:
    """How many *distinct* terms appear.

    Distinct, not total: a headline repeating one word is not more concrete than
    one that says it once, and counting occurrences lets a single repeated noun
    max a term out on its own.
    """
    return len({m.group(0).lower() for m in pattern.finditer(text)})
