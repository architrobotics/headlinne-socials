"""Tagged links, and the surfaces that honestly cannot carry one.

The test that matters most in this file is the one asserting Instagram returns
None. It would be trivially easy to hand every slot a tagged URL and report 100%
attribution coverage - the code would be simpler, the dashboard would look
better, and three quarters of the numbers would be fiction, because an Instagram
caption has no clickable link and a URL printed in one is never resolved by
anybody.
"""

from __future__ import annotations

from datetime import date
from urllib.parse import parse_qs, urlsplit

from headlinne.config import TWITTER_LIMIT, WEBSITE
from headlinne.cmo import attribution
from headlinne.cmo.attribution import Link

DAY = date(2026, 9, 14)


# --------------------------------------------------------------------------- #
# What can and cannot be tagged
# --------------------------------------------------------------------------- #
def test_a_clickable_surface_gets_a_tagged_link():
    url = attribution.for_slot(DAY, "linkedin")
    query = parse_qs(urlsplit(url).query)
    assert query["utm_source"] == ["linkedin"]
    assert query["utm_medium"] == ["post"]
    assert query["utm_campaign"] == ["2026-09"]
    assert query["utm_content"] == ["2026-09-14-linkedin"]


def test_instagram_gets_no_link_because_instagram_has_no_link():
    """Not a caption link, not a reel link, not a story card link. The only
    clickable link on the account is the bio, it is the same for every post, and
    the Graph API cannot change it."""
    for slot in ("reel_1", "reel_2", "instagram_1", "instagram_2", "story_card"):
        assert attribution.for_slot(DAY, slot) is None, slot


def test_an_untaggable_slot_prints_exactly_what_it_printed_before():
    """The fallback has to be byte-identical to the old behaviour, or the
    attribution layer becomes a copy change nobody asked for."""
    assert attribution.display_for(DAY, "reel_1") == WEBSITE
    assert attribution.display_for(DAY, "instagram_1") == WEBSITE


def test_an_unknown_slot_is_untaggable_rather_than_guessed_at():
    assert attribution.for_slot(DAY, "carrier_pigeon") is None
    assert attribution.display_for(DAY, "carrier_pigeon") == WEBSITE


# --------------------------------------------------------------------------- #
# The character budget on X
# --------------------------------------------------------------------------- #
def test_x_gets_the_compact_form_because_characters_are_the_constraint():
    url = attribution.for_slot(DAY, "x_1")
    assert "utm_" not in url
    assert parse_qs(urlsplit(url).query)["r"] == ["x1-0914"]


def test_the_compact_form_costs_a_fraction_of_the_full_one():
    """A full UTM string is about a third of a 280 character post, spent on
    something the reader never sees."""
    compact = attribution.for_slot(DAY, "x_1")
    full = attribution.for_slot(DAY, "linkedin")
    assert len(compact) < 40
    assert len(full) > 100
    # What it actually costs the post, against the bare wordmark it replaces.
    assert len(compact) - len(WEBSITE) < 25
    assert len(compact) < TWITTER_LIMIT // 6


def test_the_compact_code_still_identifies_the_slot_the_day_and_the_arm():
    assert attribution.ref_for(DAY, "x_1") == "x1-0914"
    assert attribution.ref_for(DAY, "x_2", arm="b") == "x2-0914.b"
    assert attribution.ref_for(DAY, "linkedin") == "li-0914"


def test_two_slots_on_the_same_day_are_told_apart():
    assert attribution.for_slot(DAY, "x_1") != attribution.for_slot(DAY, "x_2")


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #
def test_the_same_post_always_produces_the_same_url():
    """A regenerated day must not fork its own attribution."""
    assert attribution.for_slot(DAY, "linkedin") == attribution.for_slot(DAY, "linkedin")
    assert attribution.for_slot(DAY, "x_1") == attribution.for_slot(DAY, "x_1")


def test_the_parameter_order_does_not_depend_on_dictionary_ordering():
    url = attribution.tag("https://headlinne.com", source="s", medium="m",
                          campaign="c", content="k", term="t")
    keys = [p.split("=")[0] for p in urlsplit(url).query.split("&")]
    assert keys == sorted(keys)


def test_an_existing_query_string_survives_tagging():
    url = attribution.tag("https://headlinne.com/story?id=7", source="x",
                          medium="post", campaign="c", content="k")
    query = parse_qs(urlsplit(url).query)
    assert query["id"] == ["7"]
    assert query["utm_source"] == ["x"]


def test_an_experiment_arm_rides_along_only_when_there_is_one():
    assert "utm_term" not in attribution.for_slot(DAY, "linkedin")
    assert "utm_term=b" in attribution.for_slot(DAY, "linkedin", arm="b")


# --------------------------------------------------------------------------- #
# The finding
# --------------------------------------------------------------------------- #
def test_coverage_reports_the_share_of_a_day_that_can_be_measured_at_all():
    coverage = attribution.coverage(
        ["reel_1", "instagram_1", "story_card", "x_1", "x_2", "linkedin"])
    assert coverage.share == 0.5
    assert set(coverage.blind) == {"reel_1", "instagram_1", "story_card"}
    assert "cannot be observed" in coverage.summary()


def test_the_pipeline_as_it_runs_today_is_half_blind():
    """Three of the six things made every day go to surfaces where their
    contribution cannot be seen. That is the finding, not a bug in the report."""
    from headlinne.cmo import portfolio

    coverage = attribution.coverage(portfolio.DEFAULT_SLOTS)
    assert coverage.share < 1.0
    assert "instagram" in " ".join(
        attribution.SURFACES[s].source for s in coverage.blind)


def test_a_fully_clickable_day_says_so_without_hedging():
    coverage = attribution.coverage(["x_1", "linkedin", "reddit"])
    assert coverage.share == 1.0
    assert "every one" in coverage.summary()


def test_every_surface_declares_whether_it_can_be_tagged():
    for slot, surface in attribution.SURFACES.items():
        assert isinstance(surface.link, Link), slot
        assert surface.source and surface.medium
        # A compact surface needs a code, or its ref collides with the slot name.
        if surface.compact:
            assert surface.code, slot
