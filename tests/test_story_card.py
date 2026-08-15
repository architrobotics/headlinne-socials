"""The daily story card.

The card is one claim and the evidence for it: a kicker naming what the reader
is looking at, a headline that has to stand on its own, and the receipt strip
showing who reported the story and how many of them agree. These tests hold the
receipt honest, because the strip is the only part of the post making a claim
about our sourcing - a strip that is never thin is a strip that means nothing.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from headlinne.config import SLIDE_H, SLIDE_W
from headlinne.generate.story_card import pick_story
from headlinne.models import NewsDigest, StoryCard
from headlinne.quality import check_story_card
from headlinne.render.story_card import CARD_KINDS, _card_kind, render_story_card
from tests.helpers import make_story


def _card(**overrides) -> StoryCard:
    base = dict(
        slot="story_card", category="Finance", kind="brief",
        headline="The rate decision that changes your loan",
        standfirst="A single vote this week reaches your payment by autumn.",
        steps=[], caption="Caption.", hashtags=["Finance"],
        sources="Reuters, BBC +2",
        outlets=["Reuters", "BBC", "AP", "FT"], agree=4,
        scheduled_time="2026-08-10T21:30:00+05:30",
    )
    base.update(overrides)
    return StoryCard(**base)


def _digest() -> NewsDigest:
    return NewsDigest(
        day="2026-08-10",
        by_category={
            "Technology": [make_story("Tech one", category="Technology", score=9.0)],
            "Finance": [make_story("Money one", category="Finance", score=7.0)],
            "Geopolitics": [make_story("World one", category="Geopolitics", score=5.0)],
        },
        category_weights={}, dominant_category="Technology")


# --------------------------------------------------------------------------- #
# Choosing the story
# --------------------------------------------------------------------------- #
def test_the_card_avoids_the_category_the_reel_already_took():
    # Otherwise the day spends two of its formats on the same event.
    story = pick_story(_digest(), prefer_other_than="Technology")
    assert story.category == "Finance"


def test_an_excluded_story_is_never_reused():
    digest = _digest()
    excluded = digest.by_category["Technology"][0].url
    story = pick_story(digest, exclude_urls={excluded})
    assert story.url != excluded


def test_no_story_available_returns_none():
    empty = NewsDigest(day="2026-08-10",
                       by_category={"Technology": [], "Finance": [],
                                    "Geopolitics": []},
                       category_weights={}, dominant_category="Technology")
    assert pick_story(empty) is None


# --------------------------------------------------------------------------- #
# The three cards
# --------------------------------------------------------------------------- #
def test_each_card_has_its_own_kicker_pose_and_accent():
    # A regular reader learns the kind of story from the character and the
    # colour before reading a word, which only works if they never collide.
    seen = {name: _card_kind(_card(kind=name)) for name in CARD_KINDS}
    assert len({k for k, _, _ in seen.values()}) == len(CARD_KINDS)
    assert len({p for _, p, _ in seen.values()}) == len(CARD_KINDS)
    assert len({t for _, _, t in seen.values()}) == len(CARD_KINDS)


def test_an_unknown_kind_falls_back_to_the_brief():
    assert _card_kind(_card(kind="nonsense"))[0] == CARD_KINDS["brief"][0]


def test_a_sensitive_story_carries_no_mascot():
    # Deaths and disasters are reported plainly: no Pip, whatever the kind.
    card = _card()
    card.sensitive = True
    assert _card_kind(card)[1] is None


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def test_the_story_gets_a_carousel_of_its_own():
    # The counterweight to the twice-weekly brief: that one is many stories a
    # page each, this is one story given room.
    from PIL import Image

    with tempfile.TemporaryDirectory() as tmp:
        paths = render_story_card(_card(), Path(tmp))
        assert len(paths) >= 3
        for path in paths:
            assert path.exists()
            with Image.open(path) as img:
                assert img.size == (SLIDE_W, SLIDE_H)


def test_every_kind_and_category_renders():
    with tempfile.TemporaryDirectory() as tmp:
        for i, (kind, category) in enumerate(
                (("brief", "Technology"), ("breaking", "Finance"),
                 ("disagree", "Geopolitics"), ("brief", "Science"))):
            card = _card(kind=kind, category=category)
            paths = render_story_card(card, Path(tmp) / str(i))
            assert all(p.stat().st_size > 0 for p in paths)


def test_a_long_headline_still_renders_inside_the_frame():
    long_card = _card(headline="Two outlets read the same memo and came away "
                               "with numbers eight thousand jobs apart")
    from PIL import Image

    with tempfile.TemporaryDirectory() as tmp:
        paths = render_story_card(long_card, Path(tmp))
        with Image.open(paths[0]) as img:
            assert img.size == (SLIDE_W, SLIDE_H)


# --------------------------------------------------------------------------- #
# Quality gate
# --------------------------------------------------------------------------- #
def test_a_card_with_nothing_behind_the_receipt_is_rejected():
    # The strip would be a single outlined tick, which is an admission.
    card = _card(outlets=[], agree=0, image_file="x.png")
    assert not check_story_card(card).ok


def test_a_card_claiming_more_agreement_than_it_has_is_rejected():
    card = _card(outlets=["Reuters", "BBC"], agree=5, image_file="x.png")
    assert not check_story_card(card).ok


def test_a_complete_card_passes():
    assert check_story_card(_card(image_file="x.png")).ok


def test_missing_artwork_is_only_a_problem_when_rendering_was_asked_for():
    card = _card()  # no image_file
    assert not check_story_card(card).ok
    # `generate --no-render` deliberately produces text without artwork, so the
    # gate must not treat that as a broken card.
    assert check_story_card(card, require_media=False).ok


def test_the_daily_carousel_is_always_the_designed_five():
    # A set that is sometimes three pages and sometimes five stops being a
    # format the audience recognises.
    import tempfile as _t
    with _t.TemporaryDirectory() as tmp:
        assert len(render_story_card(_card(), Path(tmp))) == 5
        assert len(render_story_card(_card(standfirst="", headline="4 tonnes hit the Moon"),
                                     Path(tmp) / "b")) == 5
