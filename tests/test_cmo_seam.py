"""The seam: what changes when a brief exists, and what must not when it does not.

The growth layer is allowed to steer the content factory. It is not allowed to
break it. Every test here is a version of the same question - if the CMO were
deleted, or failed, or produced nonsense, would today's posts still go out and
would they look the same?

The other half is the cost the layer imposes when it does work. A tagged link is
longer than `HEADLINNE.com`, and on X those characters come straight out of the
280 the post has to say something in. The limit is a hard guarantee elsewhere in
this repository, so it has to survive attribution too.
"""

from __future__ import annotations

from datetime import date

from headlinne.config import TWITTER_LIMIT, WEBSITE
from headlinne.cmo import attribution
from headlinne.generate.common import (assemble_news_post, build_tail,
                                       fit_simple)

DAY = date(2026, 9, 14)
LEAD = "Three things moved markets today"
ITEMS = ["The central bank held rates for a fourth meeting",
         "Oil fell four percent on supply news",
         "A chipmaker guided below consensus"]


# --------------------------------------------------------------------------- #
# With no brief, nothing changes at all
# --------------------------------------------------------------------------- #
def test_an_untagged_tail_is_byte_identical_to_the_old_behaviour():
    """The fallback is what a day without a brief produces, and it has to be
    exactly what the pipeline produced before the layer existed."""
    assert build_tail(["Tech"], 1) == build_tail(["Tech"], 1, None)
    assert build_tail([], 0) == WEBSITE
    assert WEBSITE in build_tail(["Tech", "AI"], 2)


def test_an_untagged_post_is_identical_to_one_generated_before_the_layer():
    assert (assemble_news_post(LEAD, ITEMS, ["Finance"])
            == assemble_news_post(LEAD, ITEMS, ["Finance"], None))
    assert (fit_simple("Markets had a calm day.", ["Finance"])
            == fit_simple("Markets had a calm day.", ["Finance"], None))


def test_a_missing_brief_leaves_the_copy_pointing_at_the_bare_wordmark():
    post = assemble_news_post(LEAD, ITEMS, ["Finance"], None)
    assert WEBSITE in post
    assert "utm_" not in post and "?r=" not in post


# --------------------------------------------------------------------------- #
# With a brief, the link is carried and the limit still holds
# --------------------------------------------------------------------------- #
def test_a_tagged_link_reaches_the_post():
    link = attribution.for_slot(DAY, "x_1")
    post = assemble_news_post(LEAD, ITEMS, ["Finance"], link)
    assert link in post


def test_the_280_character_limit_survives_attribution():
    """The limit is a hard guarantee elsewhere in this repository. A longer tail
    has to cost body text, never the guarantee."""
    link = attribution.for_slot(DAY, "x_1")
    long_lead = "Markets moved sharply in several directions at once today " * 4
    for hashtags in ([], ["Finance"], ["Finance", "Markets", "Tech"]):
        assert len(assemble_news_post(long_lead, ITEMS, hashtags, link)) <= TWITTER_LIMIT
        assert len(fit_simple(long_lead, hashtags, link)) <= TWITTER_LIMIT


def test_a_long_link_costs_body_text_rather_than_breaking_the_limit():
    """The full UTM form is deliberately not used on X, and this is why.

    A post short enough to fit either way pays nothing, so the trade only shows
    on content that fills the limit. There, the extra characters come out of the
    news: items get dropped. The limit itself never bends.
    """
    full = attribution.for_slot(DAY, "linkedin")      # ~110 characters of tail
    assert len(full) > 100
    lead = "Markets moved in several directions at once and here is what did it"
    tagged = assemble_news_post(lead, ITEMS, ["Finance"], full)
    plain = assemble_news_post(lead, ITEMS, ["Finance"], None)

    assert len(tagged) <= TWITTER_LIMIT
    assert len(plain) <= TWITTER_LIMIT
    # The news is what pays for the tracking.
    assert tagged.count("•") < plain.count("•")


def test_the_compact_form_costs_the_post_far_less_than_the_full_one():
    """The reason X gets `?r=x1-0914` instead of five UTM parameters."""
    lead = "Markets moved in several directions at once and here is what did it"
    compact = attribution.for_slot(DAY, "x_1")
    full = attribution.for_slot(DAY, "linkedin")

    plain = assemble_news_post(lead, ITEMS, ["Finance"], None)
    with_compact = assemble_news_post(lead, ITEMS, ["Finance"], compact)
    with_full = assemble_news_post(lead, ITEMS, ["Finance"], full)

    # The compact form keeps every item the untagged post kept.
    assert with_compact.count("•") == plain.count("•")
    assert with_full.count("•") < with_compact.count("•")


# --------------------------------------------------------------------------- #
# The generators thread it through
# --------------------------------------------------------------------------- #
def test_linkedin_puts_the_tagged_link_in_the_call_to_action():
    from headlinne.generate.linkedin import _assemble

    link = attribution.for_slot(DAY, "linkedin")
    post = _assemble({"title": "T", "body": "B", "cta": ""}, DAY,
                     kind="product", link=link)
    assert link in post.cta


def test_linkedin_without_a_link_still_points_at_the_website():
    from headlinne.generate.linkedin import _assemble

    post = _assemble({"title": "T", "body": "B", "cta": ""}, DAY, kind="product")
    assert WEBSITE in post.cta
    assert "utm_" not in post.cta


def test_the_generators_accept_an_absent_brief_without_complaint():
    """`links` is always optional and an empty dict must behave as None."""
    from headlinne.generate import linkedin, twitter

    import inspect

    for func in (twitter.generate_news, twitter.generate_promo,
                 linkedin.generate):
        params = inspect.signature(func).parameters
        assert "links" in params, func.__name__
        assert params["links"].default is None, func.__name__


# --------------------------------------------------------------------------- #
# Instagram is left exactly as it was
# --------------------------------------------------------------------------- #
def test_no_instagram_surface_is_given_a_link_it_cannot_use():
    """A URL with tracking parameters printed in an Instagram caption is worse
    than the bare domain: longer, uglier, not clickable, and never typed."""
    for slot in ("reel_1", "reel_2", "instagram_1", "instagram_2", "story_card"):
        assert attribution.for_slot(DAY, slot) is None
        assert attribution.display_for(DAY, slot) == WEBSITE
