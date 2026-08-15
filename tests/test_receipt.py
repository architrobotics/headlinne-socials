"""The source strip must never overstate coverage.

The denominator is the thing that decides whether this component earns trust or
destroys it, so it is asserted rather than assumed.
"""

from __future__ import annotations

from headlinne.models import Story
from headlinne.render import receipt as R


def _s(source, corroborating=()):
    return Story(title="A thing happened", summary="", url="https://x/1",
                 category="Science", source=source, tier=1.2,
                 published_iso="2026-08-15T09:00:00+00:00",
                 corroborating_sources=list(corroborating))


def test_the_count_is_outlets_that_reported_not_feeds_we_read():
    story = _s("Reuters", ["AP", "BBC World"])
    assert R.label(story) == "3 outlets reported this"
    assert "32" not in R.label(story)


def test_a_single_source_says_so_and_draws_one_outlined_tick():
    story = _s("Reuters")
    assert R.ticks(story) == (0, 1)
    assert "Single source" in R.label(story)


def test_the_original_outlet_is_counted_once_even_if_repeated():
    story = _s("Reuters", ["Reuters", "AP"])
    assert R.outlets(story) == ["Reuters", "AP"]
    assert R.label(story) == "2 outlets reported this"


def test_ticks_never_exceed_what_can_be_counted_at_a_glance():
    story = _s("Reuters", [f"Outlet {i}" for i in range(20)])
    filled, outlined = R.ticks(story)
    assert filled == R.MAX_TICKS and outlined == 0
    assert R.overflow(story) == 21 - R.MAX_TICKS


def test_named_outlets_overflow_honestly():
    story = _s("Reuters", ["AP", "BBC", "Sky", "NPR"])
    assert R.named(story, limit=3) == "Reuters · AP · BBC +2"
