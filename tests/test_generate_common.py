"""X posts must never exceed 280 characters once the website and hashtags are
appended. These tests prove the fitters always stay within the limit and drop
list items before truncating mid-word."""

from __future__ import annotations

from headlinne.config import TWITTER_LIMIT, WEBSITE
from headlinne.generate.common import (
    assemble_news_post,
    build_tail,
    fit_simple,
    hashtag,
)


def test_hashtag_formatting():
    assert hashtag("AI") == "#AI"
    assert hashtag("#Tech") == "#Tech"
    assert hashtag("World News") == "#WorldNews"


def test_build_tail_includes_website():
    tail = build_tail(["Tech", "AI"], 2)
    assert tail.startswith(WEBSITE)
    assert "#Tech" in tail and "#AI" in tail


def test_fit_simple_short_body_under_limit():
    out = fit_simple("Markets had a calm and steady day.", ["Finance", "Markets"])
    assert len(out) <= TWITTER_LIMIT
    assert WEBSITE in out


def test_fit_simple_long_body_is_trimmed_within_limit():
    body = "word " * 120  # ~600 chars, far over the limit
    out = fit_simple(body, ["Tech", "AI", "News"])
    assert len(out) <= TWITTER_LIMIT
    assert WEBSITE in out
    # Trimming should not leave a dangling partial-word with trailing space junk.
    assert not out.endswith(" ")


def test_assemble_news_post_stays_within_limit():
    lead = "Today's top tech stories"
    items = [
        "A major chipmaker announced a powerful new processor for data centers",
        "A large social platform rolled out new privacy controls for everyone",
        "A popular AI tool added support for many additional languages today",
    ]
    out = assemble_news_post(lead, items, ["Tech", "AI"])
    assert len(out) <= TWITTER_LIMIT
    assert WEBSITE in out
    assert "\u2022" in out  # at least one bullet survived


def test_assemble_drops_items_when_too_long():
    lead = "Today's top stories"
    long_items = [("This is a very long story description number %d that keeps "
                   "going on well past what could fit" % i) for i in range(3)]
    out = assemble_news_post(lead, long_items, ["Tech"])
    assert len(out) <= TWITTER_LIMIT
    # With items this long, not all three bullets can fit.
    assert out.count("\u2022") < 3


def test_assemble_news_post_has_no_forbidden_punctuation():
    out = assemble_news_post(
        "Big day in finance",
        ["Stocks climbed; bonds slipped \u2014 a mixed session overall"],
        ["Finance"],
    )
    assert ";" not in out
    assert "\u2014" not in out
