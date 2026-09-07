"""Correcting a category the feed got wrong.

A story's category comes from the feed it arrived on, and general feeds carry
everything. The label picks the hashtags, sets the eyebrow, and feeds the day's
category weights - so a wrong one is visible on the post and steers what the
next format is allowed to cover.

These tests pin the shape of the rule as much as its output: the feed's label is
the default, and it only loses to clear evidence.
"""

from __future__ import annotations

from headlinne.news.categorise import MIN_EVIDENCE, evidence, recategorise


def test_a_discovery_filed_on_a_world_news_feed_is_corrected():
    """This one published. "Scientists discover new 'immune hubs' in skull bone
    marrow" went out under Geopolitics, with Geopolitics hashtags."""
    assert recategorise(
        "Scientists discover new 'immune hubs' in skull bone marrow",
        current="Geopolitics") == "Science"


def test_an_earnings_story_on_a_tech_feed_is_corrected():
    assert recategorise(
        "SpaceX doubles revenue on compute deals, earnings show",
        current="Technology") == "Finance"


def test_a_story_showing_its_own_colours_keeps_its_label():
    """Evidence for the assigned category ends the question, whatever else the
    headline mentions. A tariff story on a finance feed is a finance story."""
    assert recategorise(
        "Tariff refund ignites profit spike as quarterly revenue beats forecasts",
        current="Finance") == "Finance"


def test_one_passing_mention_is_not_enough_to_move_a_story():
    """A single term is as likely to be a passing reference as a subject, and a
    wrong correction is worse than the label we already had."""
    title = "Voters weigh a study of election turnout"
    assert max(evidence(title).values()) < MIN_EVIDENCE or \
        recategorise(title, current="Geopolitics") == "Geopolitics"


def test_a_genuinely_mixed_headline_keeps_the_feed_label():
    """Equal evidence for two categories is a coin flip, and the feed already
    made a better-informed guess than a coin."""
    mixed = ("Semiconductor export sanctions and a chipset embargo follow the "
             "summit, with treaty talks on encryption")
    assert recategorise(mixed, current="Finance") == "Finance"


def test_an_unclassifiable_headline_is_left_alone():
    for title in ("Prince William to attend King Harald's funeral in Norway",
                  "Two unvaccinated people die of measles in Pennsylvania"):
        assert recategorise(title, current="Geopolitics") == "Geopolitics"


def test_the_correction_reaches_the_digest():
    from headlinne.news.ranking import rank
    from tests.helpers import make_story

    story = make_story(
        "Astronomers find an exoplanet orbiting a distant galaxy's black hole",
        category="Geopolitics", source="Phys.org")
    digest = rank([story])
    placed = [s for v in digest.by_category.values() for s in v]
    assert placed and placed[0].category == "Science"
