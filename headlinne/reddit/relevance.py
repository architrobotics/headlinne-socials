"""Deciding whether a thread is worth engaging, and whether it is safe to.

All pure functions, no network, so the judgement that keeps the tool on the
right side of Reddit's rules is fully unit-tested. Two jobs:

1. Relevance: does this thread actually relate to what Headlinne helps with
   (keeping up with the news, news overload, bias, personalised feeds)? A reply
   is only worth drafting where we can genuinely add value.
2. Safety: is the thread sensitive (grief, medical, tragedy)? Those never get a
   promotional angle, and usually should be left alone entirely.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from ..config import (REDDIT_KEYWORDS, REDDIT_MAX_THREAD_AGE_HOURS,
                      REDDIT_MIN_COMMENTS, REDDIT_MIN_THREAD_AGE_HOURS,
                      REDDIT_SENSITIVE_MARKERS)
from .models import RedditThread

# Words that describe what Headlinne is genuinely useful for. Overlap with these
# (on top of the search keywords) is what makes a thread a real fit rather than
# just topically adjacent.
_VALUE_TERMS = (
    "news", "headlines", "informed", "keep up", "overwhelmed", "overload",
    "bias", "biased", "unbiased", "aggregator", "feed", "personalised",
    "personalized", "summary", "summaries", "app", "sources", "doomscroll",
    "fatigue", "curate", "curated", "digest",
)

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


def topic_relevance(title: str, body: str = "") -> float:
    """A 0..1 score of how well a thread matches what Headlinne helps with.

    Blends whole-phrase keyword hits (strong signal) with single value-term
    overlap (weaker signal), so 'how do you keep up with the news?' scores high
    while a random tech headline scores low.
    """
    text = f"{title} {body}".lower()
    toks = set(_tokens(text))
    if not toks:
        return 0.0

    phrase_hits = sum(1 for kw in REDDIT_KEYWORDS if kw in text)
    term_hits = sum(1 for t in _VALUE_TERMS if t in toks)

    # Phrases are worth a lot (they signal genuine intent), terms a little.
    score = phrase_hits * 0.34 + term_hits * 0.08
    # A question about keeping informed is an especially good fit.
    if "?" in title and any(t in text for t in ("news", "informed", "keep up")):
        score += 0.15
    return max(0.0, min(1.0, score))


def is_sensitive(title: str, body: str = "") -> bool:
    """True if the thread touches a sensitive topic. Such threads never get a
    promotional angle and are usually skipped entirely."""
    text = f"{title} {body}".lower()
    return any(marker in text for marker in REDDIT_SENSITIVE_MARKERS)


def _age_hours(thread: RedditThread, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    created = datetime.fromtimestamp(thread.created_utc, tz=timezone.utc)
    return max(0.0, (now - created).total_seconds() / 3600.0)


def thread_is_engageable(thread: RedditThread, now: datetime | None = None,
                         *, min_relevance: float = 0.3) -> tuple[bool, str]:
    """Whether a thread passes the basic gates for a helpful reply.

    Returns (ok, reason). Reason explains the rejection for the review log.
    """
    if thread.locked:
        return False, "thread is locked"
    if thread.over_18:
        return False, "thread is marked NSFW"
    if thread.num_comments < REDDIT_MIN_COMMENTS:
        return False, f"too few comments ({thread.num_comments})"
    age = _age_hours(thread, now)
    if age < REDDIT_MIN_THREAD_AGE_HOURS:
        return False, "thread is too new to have a discussion yet"
    if age > REDDIT_MAX_THREAD_AGE_HOURS:
        return False, f"thread is too old ({age:.0f}h), a reply would be buried"
    rel = topic_relevance(thread.title, thread.selftext)
    if rel < min_relevance:
        return False, f"not relevant enough ({rel:.2f})"
    return True, "ok"
