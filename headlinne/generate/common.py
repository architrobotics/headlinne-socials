"""Helpers shared by the per-platform generators.

Length fitting for X lives here (the model writes prose, this code guarantees
the 280-character limit and keeps roughly the final 30 characters for the
website and hashtags). Feature/topic rotations keep promo and LinkedIn content
varied across days.
"""

from __future__ import annotations

from ..config import TWITTER_LIMIT, WEBSITE
from ..quality.sanitize import sanitize

# Rotations (indexed by day ordinal) so content does not repeat itself.
PROMO_FEATURES = [
    "AI Search that answers detailed questions with linked sources",
    "Deep Dive Mode with visual aids and conversational follow-up questions",
    "personalised recommendations that learn from what you read",
    "clear AI summaries of every article",
    "political bias analysis on stories",
    "swipe-based discovery, swipe to like, skip or open the full story",
    'the "Why It Matters" explanation on each story',
]

LINKEDIN_TOPICS = [
    "how a recommendation engine learns what each reader actually cares about",
    "what AI Search changes about how people find answers in the news",
    "why Deep Dive Mode helps people understand a story, not just read it",
    "the case for truly personalised news feeds",
    "the product philosophy behind a calmer, smarter news experience",
    "the founder journey of building a news app as a teenager",
    "an interesting engineering decision behind the feed",
    "where personalised news goes next, a look at the roadmap",
    "why personalised news matters for staying genuinely informed",
]


def clamp_words(text: str, max_chars: int) -> str:
    """Trim to a word boundary under `max_chars`.

    Used wherever generated text is drawn into a fixed space (cover titles, reel
    captions, story card steps). The renderer would shrink the type to fit
    instead, but past a certain length that produces a slide nobody reads, so we
    cut at the source.
    """
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return cut.rstrip(",.:;- ").strip() or text[:max_chars]


def hashtag(word: str) -> str:
    return "#" + str(word).lstrip("#").replace(" ", "")


def build_tail(hashtags: list[str], n_tags: int, link: str | None = None) -> str:
    """The closing line: where to go, then the tags.

    `link` is the CMO's tagged URL for this slot. It defaults to the bare
    wordmark, which is exactly what this printed before the attribution layer
    existed, so a day generated without a brief is byte-identical to one
    generated last week.

    A tagged link is longer than `HEADLINNE.com` and that cost is real: it comes
    out of the 280 characters the post has to say something in. The fitters
    below measure the assembled string rather than trusting a reserved constant,
    so a longer tail costs body text instead of silently breaking the limit.
    """
    tags = " ".join(hashtag(h) for h in hashtags[:n_tags] if str(h).strip())
    return ((link or WEBSITE) + (" " + tags if tags else "")).strip()


def fit_simple(body: str, hashtags: list[str], link: str | None = None) -> str:
    """Fit a single body + tail under the X limit, trimming only as last resort."""
    body = body.strip()
    for n in (2, 1, 0):
        full = (body + " " + build_tail(hashtags, n, link)).strip()
        if len(full) <= TWITTER_LIMIT:
            return full
    tail = build_tail(hashtags, 0, link)
    room = TWITTER_LIMIT - len(tail) - 1
    trimmed = body[: max(0, room)].rsplit(" ", 1)[0].rstrip(",.:;- ")
    return (trimmed + " " + tail).strip()


def assemble_news_post(lead: str, items: list[str], hashtags: list[str],
                       link: str | None = None) -> str:
    """Assemble a multi-line news post, dropping items before truncating."""
    lead = sanitize(lead).strip().rstrip(":")
    clean_items = [sanitize(i).strip().rstrip(".") for i in items if i and i.strip()][:3]

    best = ""
    for k in range(len(clean_items), -1, -1):
        lines = [lead] + ["\u2022 " + it for it in clean_items[:k]]
        body = "\n".join(lines)
        for n in (2, 1, 0):
            full = (body + " " + build_tail(hashtags, n, link)).strip()
            if len(full) <= TWITTER_LIMIT:
                return full
        best = body
    # Should not reach here, but guarantee a valid post.
    return fit_simple(best or lead, hashtags, link)
