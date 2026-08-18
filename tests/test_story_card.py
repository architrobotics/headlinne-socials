"""The daily story card.

The format's value is that it is complete on one frame and identical in shape
every day, so these tests hold the rail to its fixed four stops and check that a
card whose text arrives long shrinks rather than truncating. A step whose last
line is silently cut is the one failure this format cannot survive, because the
cut line is usually the one carrying the point.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from headlinne.config import SLIDE_H, SLIDE_W
from headlinne.generate.story_card import (STEP_CHARS, STEP_LABELS, _steps_from,
                                           pick_story)
from headlinne.models import NewsDigest, StoryCard, StoryStep
from headlinne.quality import check_story_card
from headlinne.render.story_card import _layout_steps, render_story_card
from tests.helpers import make_story


def _card(**overrides) -> StoryCard:
    base = dict(
        slot="story_card", category="Finance",
        headline="The rate decision that changes your loan",
        standfirst="A single vote this week reaches your payment by autumn.",
        steps=[StoryStep(label, f"Text for {label.lower()}, with enough words "
                                f"in it to wrap onto a second line.")
               for label in STEP_LABELS],
        caption="Caption.", hashtags=["Finance"], sources="Reuters, BBC +2",
        scheduled_time="2026-08-10T21:30:00+05:30",
    )
    base.update(overrides)
    return StoryCard(**base)


# --------------------------------------------------------------------------- #
# Step mapping
# --------------------------------------------------------------------------- #
def test_the_rail_is_always_the_same_four_stops():
    # The model does not get to rename, reorder or add to the rail: a format
    # that drifts week to week stops being recognisable in a feed.
    steps = _steps_from({"steps": [{"label": "Something else", "text": "a"},
                                   {"label": "Another", "text": "b"}]})
    assert [s.label for s in steps] == list(STEP_LABELS)


def test_steps_are_matched_by_label_even_when_returned_out_of_order():
    steps = _steps_from({"steps": [
        {"label": "Why it matters", "text": "the effect"},
        {"label": "What happened", "text": "the event"},
    ]})
    by_label = {s.label: s.text for s in steps}
    assert by_label["What happened"] == "the event"
    assert by_label["Why it matters"] == "the effect"


def test_step_text_is_clamped_on_a_word_boundary():
    steps = _steps_from({"steps": [{"label": STEP_LABELS[0],
                                    "text": "word " * 80}]})
    assert len(steps[0].text) <= STEP_CHARS
    assert not steps[0].text.endswith(" ")


def test_missing_steps_come_back_empty_rather_than_invented():
    steps = _steps_from({})
    assert len(steps) == len(STEP_LABELS)
    assert all(s.text == "" for s in steps)


# --------------------------------------------------------------------------- #
# Story choice
# --------------------------------------------------------------------------- #
def _digest() -> NewsDigest:
    return NewsDigest(
        day="2026-08-10",
        by_category={
            "Technology": [make_story("Tech one", category="Technology", score=9.0)],
            "Finance": [make_story("Money one", category="Finance", score=7.0)],
            "Geopolitics": [],
        },
        category_weights={"Technology": 0.6, "Finance": 0.4, "Geopolitics": 0.0},
        dominant_category="Technology")


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
# Layout
# --------------------------------------------------------------------------- #
def test_no_step_ever_loses_a_line():
    # Every step at its full character budget is the worst case the generator
    # can produce, and all of it has to be drawn.
    card = _card(steps=[StoryStep(label, "w" * 8 + " " + "word " * 18)
                        for label in STEP_LABELS])
    blocks, _ = _layout_steps(card, available=600)
    for step, _font, lines, _line_h, _height in blocks:
        rendered = " ".join(lines)
        # Every word of the source text survives into the wrapped lines.
        assert len(rendered.split()) == len(step.text.split())


def test_a_long_card_shrinks_its_type_instead_of_overflowing():
    # 30 words a step is where the four blocks stop fitting at full size. Twenty
    # still fits in two lines each, so it never exercised the shrink.
    tight = _card(steps=[StoryStep(label, "word " * 30) for label in STEP_LABELS])
    roomy = _card(steps=[StoryStep(label, "short") for label in STEP_LABELS])
    tight_blocks, tight_h = _layout_steps(tight, available=600)
    roomy_blocks, roomy_h = _layout_steps(roomy, available=600)
    assert tight_h <= 600
    # The dense card is set smaller than the sparse one.
    assert tight_blocks[0][1].size < roomy_blocks[0][1].size


def test_shrinking_is_preferred_to_cutting_the_line_that_carries_the_point():
    # Truncation is the last resort, not the first. "Why it matters" is the step
    # most likely to run long and the one a reader came for.
    card = _card(steps=[StoryStep(label, "word " * 30) for label in STEP_LABELS])
    blocks, _ = _layout_steps(card, available=600)
    for step, _font, lines, _lh, _h in blocks:
        assert len(" ".join(lines).split()) == len(step.text.split())


def test_card_renders_at_the_instagram_portrait_size():
    with tempfile.TemporaryDirectory() as tmp:
        path = render_story_card(_card(), Path(tmp) / "card.png",
                                 image_loader=lambda _s: None)
        assert path.exists()
        from PIL import Image

        with Image.open(path) as img:
            assert img.size == (SLIDE_W, SLIDE_H)


def test_card_renders_for_every_category_and_without_sources():
    with tempfile.TemporaryDirectory() as tmp:
        for i, category in enumerate(("Technology", "Finance", "Geopolitics")):
            card = _card(category=category, sources="" if i == 0 else "AP")
            path = render_story_card(card, Path(tmp) / f"{i}.png",
                                     image_loader=lambda _s: None)
            assert path.stat().st_size > 0


# --------------------------------------------------------------------------- #
# Quality gate
# --------------------------------------------------------------------------- #
def test_a_half_empty_card_is_rejected():
    card = _card(steps=[StoryStep(STEP_LABELS[0], "only this one")]
                       + [StoryStep(label, "") for label in STEP_LABELS[1:]],
                 image_file="x.png")
    report = check_story_card(card)
    assert not report.ok


def test_a_complete_card_passes():
    card = _card(image_file="x.png")
    assert check_story_card(card).ok


def test_missing_artwork_is_only_a_problem_when_rendering_was_asked_for():
    card = _card()  # no image_file
    assert not check_story_card(card).ok
    # `generate --no-render` deliberately produces text without artwork, so the
    # gate must not treat that as a broken card.
    assert check_story_card(card, require_media=False).ok


def test_forbidden_punctuation_is_caught_in_a_step():
    card = _card(image_file="x.png")
    card.steps[1].text = "This has a semicolon; which is banned."
    report = check_story_card(card)
    assert not report.ok


# --------------------------------------------------------------------------- #
# Pip
# --------------------------------------------------------------------------- #
def _story(state="unanimous", sensitive=False):
    from headlinne.models import Agreement, Conflict, Story

    story = Story(title="A rocket hit the Moon", summary="", url="http://x/m",
                  category="Science", source="Reuters", tier=1.4,
                  published_iso="2026-08-18T06:00:00+00:00", verified=True,
                  sensitive=sensitive)
    if state == "unanimous":
        story.agreement = Agreement(reported=8, agree=8,
                                    outlets=[f"O{i}" for i in range(8)])
    elif state == "developing":
        story.agreement = Agreement(reported=6, agree=4,
                                    outlets=[f"O{i}" for i in range(6)])
    else:
        story.agreement = Agreement(
            reported=7, agree=3, conflict=4, claim="12,000 jobs",
            outlets=[f"O{i}" for i in range(7)],
            conflicts=[Conflict(f"O{i}", f"{i},000 jobs") for i in range(4)])
    return story


def _rendered(story):
    from PIL import Image

    from headlinne.render.story_card import render_story_card

    with tempfile.TemporaryDirectory() as tmp:
        path = render_story_card(_card(), Path(tmp) / "card.png", story=story)
        return Image.open(path).convert("RGB").copy()


def test_pip_is_actually_drawn_on_the_story_card():
    # He was not. The mascot was positioned into the gap between the header and
    # the rail, which is exactly HEAD_TO_RAIL tall, and then only drawn if that
    # gap was at least 130px - so the condition could never be true and Pip
    # silently never appeared on this surface at all.
    from headlinne.render import story_card as sc

    assert sc.PIP_BAND >= 24 * sc.PIP_SCALE, "the band cannot fit the sprite"
    assert sc.HEAD_TO_RAIL > sc.PIP_BAND, "no room reserved between the bands"

    with_pip = _rendered(_story())
    without = _rendered(_story(sensitive=True))
    assert with_pip.tobytes() != without.tobytes(), "Pip changed no pixels"


def test_a_sensitive_story_carries_neither_mascot_nor_bubble():
    from headlinne.render import theme
    from headlinne.render.story_card import pip_line

    story = _story(sensitive=True)
    assert theme.pose_for_story(story, "explainer") is None
    assert pip_line(story) == ""


def test_pip_says_something_true_about_the_sourcing():
    from headlinne.render.story_card import pip_line

    assert "8" in pip_line(_story("unanimous"))
    assert pip_line(_story("disputed")) == "They don't all agree."
    assert pip_line(_story("developing")) == "Still coming together."


def test_the_card_takes_the_brand_colour_not_the_category_colour():
    # Colour coding by desk gave a violet Science card and a green Finance one -
    # four different-looking brands in one profile grid, none of them saying
    # anything a reader can act on.
    from headlinne.config import BRAND_TERRACOTTA, CATEGORY_COLORS
    from headlinne.render import theme

    terracotta = theme.hex_to_rgb(BRAND_TERRACOTTA)
    for category in CATEGORY_COLORS:
        story = _story()
        story.category = category
        assert theme.tone_for(story, category=category) == terracotta, category


def test_a_disputed_story_still_overrides_the_brand_colour():
    from headlinne.config import TONE_DISPUTE
    from headlinne.render import theme

    assert theme.tone_for(_story("disputed")) == theme.hex_to_rgb(TONE_DISPUTE)


def test_the_rail_keeps_readable_type_now_that_pip_has_a_band():
    # Giving Pip a band takes room from the rail. The rail is the content on this
    # surface, so it must not be paying for the mascot in truncated steps.
    from headlinne.render.story_card import RAIL_BOTTOM, _layout_steps

    blocks, total = _layout_steps(_card(), available=RAIL_BOTTOM - 620)
    assert total <= RAIL_BOTTOM - 620
    for step, font, lines, _lh, _h in blocks:
        assert len(" ".join(lines).split()) == len(step.text.split())
        assert font.size >= 24, f"rail dropped to {font.size}px"
