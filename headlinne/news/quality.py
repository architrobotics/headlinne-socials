"""What is not news, however well it scores.

The interest score asks whether a person would want to read something. It has no
opinion on whether the thing is journalism, and commerce copy is engineered to be
interesting. Left to itself the ranker put these in one day's top twenty-five:

    13.  Google Workspace Promo Codes: 14% Off for August 2026
    22.  Our expert thinks this portable Celestron telescope will delight...
    12.  5 Weird Tricks for Having a Brain
    17.  On this day in space! Aug. 15, 1977: Mysterious 'Wow!' Signal
    20.  I wish I had been a more rebellious teenager, says Bella Ramsey

The existing _LOW_VALUE_MARKERS scored every one of those at 0.0 penalty, and a
soft penalty could not have saved it anyway: it caps at 2.3 against interest
scores above 11.

So this is a gate rather than a weight. A story earns a place by reporting an
event or a finding. A coupon, a product recommendation, a listicle, an
anniversary and a celebrity's feelings about their teenage years are none of
those, no matter how well they read.

Being wrong in one direction is much worse than the other. Dropping a decent
story costs one post out of a few hundred a week; publishing a promo code as
news costs the thing the whole account is for. When a rule is arguable, it
belongs in the arguable list below and is kept narrow.
"""

from __future__ import annotations

import re

# Commerce. None of this is reporting, and some of it is paid placement.
_COMMERCE = (
    "promo code", "coupon", "% off", "percent off", "discount code", "deal of",
    "best deals", "on sale now", "save up to", "lowest price", "price drop",
    "black friday", "prime day", "cyber monday", "affiliate", "buying guide",
    "shop the", "where to buy", "our expert thinks", "we recommend",
    "will delight", "worth your money", "should you buy",
)

# Reviews and product comparisons. A verdict on a phone is not an event.
_REVIEW = (
    "review:", " review ", "review]", "hands-on", "hands on with", "unboxing",
    "we tried", "i tried", "tested:", "we tested", "benchmarked",
    " vs ", " vs. ", "versus", "compared:", "which is better", "head-to-head",
    "ranked:", "the best ", "top 10 ", "top 5 ", "our favourite", "our favorite",
)

# Listicles and quizzes.
_LISTICLE = (
    "weird tricks", "things you", "ways to", "reasons why", "things to know",
    "tips for", "hacks for", "you should know", "quiz:", "explained in",
)

# Filler shapes: anniversaries, galleries, horoscopes, and celebrity feelings.
_FILLER = (
    "on this day", "years ago today", "this week in", "in pictures", "in photos",
    "photo of the", "picture of the", "horoscope", "your daily", "caption this",
    "emotional tributes", "heart breaks", "opens up about", "reveals all",
    "what they wore", "red carpet", "reacts to", "slams ", "hits back at",
)

# Aggregator furniture that is about the outlet rather than the world.
_HOUSEKEEPING = (
    "newsletter", "subscribe", "our podcast", "listen:", "watch:", "live blog",
    "live updates", "as it happened", "open thread", "weekly roundup",
    "editor's note", "correction:", "we're hiring", "sponsored", "paid post",
    "advertisement", "partner content", "promoted",
)

# Arguable. Kept deliberately narrow: these shapes are usually filler but
# occasionally carry a real finding, so only the clearest forms are listed.
_ARGUABLE = (
    "everything announced", "everything we know", "everything you need",
    "here's what we know", "rumor roundup", "leak roundup",
)

_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("commerce", _COMMERCE),
    ("review", _REVIEW),
    ("listicle", _LISTICLE),
    ("filler", _FILLER),
    ("housekeeping", _HOUSEKEEPING),
    ("arguable", _ARGUABLE),
)

# "5 Weird Tricks", "7 things", "Top 12" - a numbered list of items rather than
# a report of one thing happening.
_NUMBERED_LIST = re.compile(
    r"^\s*(?:the\s+)?\d{1,2}\s+\w+", re.I)


def reject_reason(title: str, summary: str = "") -> str | None:
    """Why this is not publishable as news, or None if it is.

    Matching is on the headline. Summaries quote and describe, so a summary
    mentioning a price does not make the story an advert, and testing against
    them produced far more false rejections than true ones.
    """
    low = f" {title.lower().strip()} "
    for name, markers in _RULES:
        for marker in markers:
            if marker in low:
                return f"{name}:{marker.strip()}"
    if _NUMBERED_LIST.match(title) and not re.match(r"^\s*\d{4}\b", title):
        return "listicle:numbered"
    return None


def is_publishable(title: str, summary: str = "") -> bool:
    return reject_reason(title, summary) is None
