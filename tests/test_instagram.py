"""The daily carousel: what earns it, and how the five slides are assembled."""

from headlinne.generate.instagram import (MIN_SOURCES_FOR_CAROUSEL,
                                          _hashtags, _slides, agreement_line,
                                          pick_story, verified_figure)
from headlinne.models import Agreement, Conflict, NewsDigest, Story


def _story(title, *, source="Reuters", score=8.0, outlets=4, agree=None,
           conflict=0, category="Science", summary="", sensitive=False,
           conflicts=()):
    names = [source] + [f"Outlet{i}" for i in range(1, outlets)]
    story = Story(title=title, summary=summary, url=f"http://x/{title[:10]}",
                  category=category, source=source, tier=1.2,
                  published_iso="2026-08-17T06:00:00+00:00",
                  corroborating_sources=names[1:], sensitive=sensitive)
    story.score = score
    story.agreement = Agreement(reported=outlets,
                                agree=outlets if agree is None else agree,
                                conflict=conflict, outlets=names,
                                conflicts=list(conflicts))
    story.verified = story.agreement.publishable
    return story


def _digest(stories):
    by_category: dict[str, list[Story]] = {}
    for s in stories:
        by_category.setdefault(s.category, []).append(s)
    return NewsDigest(day="2026-08-17", by_category=by_category,
                      category_weights={}, dominant_category="Science")


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #
def test_the_best_well_sourced_story_wins():
    best = _story("Rocket hits the Moon", score=9.0, outlets=5)
    thin = _story("Something else entirely", score=9.9, outlets=1)
    assert pick_story(_digest([thin, best])) is best


def test_a_thinly_sourced_story_never_gets_five_slides():
    # Four of the five slides make claims the source strip has to back, so the
    # bar is higher here than the two-source publishing bar.
    thin = _story("Single-source scoop", score=9.9, outlets=1)
    assert pick_story(_digest([thin])) is None


def test_it_falls_back_to_the_best_verified_story_rather_than_nothing():
    two = _story("Two outlets have it", score=7.0, outlets=2)
    assert pick_story(_digest([two])) is two
    assert two.agreement.reported < MIN_SOURCES_FOR_CAROUSEL


def test_the_reel_story_is_excluded_so_the_day_does_not_repeat_itself():
    a = _story("Story A", score=9.0, outlets=5)
    b = _story("Story B", score=8.0, outlets=5)
    assert pick_story(_digest([a, b]), exclude_urls={a.url}) is b


# --------------------------------------------------------------------------- #
# Figures
# --------------------------------------------------------------------------- #
def test_a_figure_must_appear_in_the_story_to_be_set_at_280px():
    story = _story("Rocket hits the Moon at 8,700 km/h",
                   summary="Four tonnes, travelling at 8,700 km/h.")
    assert verified_figure("8700", story) == "8700"
    assert verified_figure("8,700", story) == "8,700"
    assert verified_figure("12000", story) == "", "invented figures are dropped"


def test_a_spelled_out_number_is_accepted_when_the_digit_is_in_the_story():
    story = _story("A four-tonne stage", summary="The 4 tonne upper stage.")
    assert verified_figure("four", story) == "four"


def test_an_empty_figure_is_not_an_error():
    assert verified_figure("", _story("No numbers here")) == ""


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #
_MODEL_OUTPUT = {
    "cover_headline": "A rocket just hit the Moon",
    "cover_sub": "8,700 km/h. Nobody meant to do it.",
    "cover_say": "Something hit the Moon.",
    "figure": "8700", "unit": "km/h",
    "scale_text": "About six times the speed of a rifle bullet.",
    "twist_headline": "In 2022 everyone blamed the wrong rocket",
    "twist_text": "The correction took months.",
    "twist_say": "Here is the bit I like.",
    "sources_text": "Every outlet covering it agrees on the speed.",
    "cta_sub": "Every source, side by side.",
}


def test_the_five_roles_are_produced_in_order():
    story = _story("Rocket hits the Moon at 8700 km/h",
                   summary="It struck at 8700 km/h.")
    slides = _slides(_MODEL_OUTPUT, story)
    assert [s.role for s in slides] == ["cover", "scale", "twist", "sources", "cta"]
    assert [s.index for s in slides] == [1, 2, 3, 4, 5]


def test_the_scale_slide_keeps_the_number_and_the_unit_apart():
    story = _story("Rocket hits at 8700 km/h", summary="8700 km/h.")
    scale = _slides(_MODEL_OUTPUT, story)[1]
    assert scale.figure == "8700"
    assert scale.unit == "km/h"


def test_an_unverified_figure_takes_its_unit_with_it():
    story = _story("A rocket hit the Moon", summary="No figures at all.")
    scale = _slides(_MODEL_OUTPUT, story)[1]
    assert scale.figure == ""
    assert scale.unit == "", "a unit with no number is furniture around nothing"


def test_a_sensitive_story_carries_no_mascot_and_no_speech():
    story = _story("Ferry capsizes, 40 dead", sensitive=True,
                   category="Geopolitics")
    for slide in _slides(_MODEL_OUTPUT, story):
        assert slide.pose == "", f"{slide.role} kept a pose"
        assert slide.say == "", f"{slide.role} kept a speech bubble"


def test_a_disputed_story_puts_pip_in_the_puzzled_pose():
    story = _story("Same memo, two numbers", outlets=7, agree=3, conflict=4,
                   conflicts=[Conflict("FT", "4,000 jobs")])
    slides = _slides(_MODEL_OUTPUT, story)
    assert slides[0].pose == "puzzled"
    assert slides[0].kicker == "SOURCES DISAGREE"


def test_a_unanimous_story_uses_the_category_as_its_kicker():
    story = _story("Rocket hits the Moon", category="Science")
    assert _slides(_MODEL_OUTPUT, story)[0].kicker == "SCIENCE"


def test_the_cover_falls_back_to_the_story_headline():
    story = _story("The real headline")
    slides = _slides({}, story)
    assert slides[0].headline == "The real headline"


# --------------------------------------------------------------------------- #
# Sourcing described to the model
# --------------------------------------------------------------------------- #
def test_the_agreement_line_names_the_outlets():
    story = _story("Rocket hits the Moon", outlets=4)
    line = agreement_line(story)
    assert "4 of 4 outlets agree" in line
    assert "Reuters" in line


def test_a_disputed_agreement_line_states_both_figures():
    story = _story("Same memo", outlets=7, agree=3, conflict=4,
                   conflicts=[Conflict("FT", "4,000 jobs")])
    story.agreement.claim = "12,000 jobs"
    line = agreement_line(story)
    assert "3 of 7" in line
    assert "FT says 4,000 jobs" in line


def test_hashtags_are_deduplicated_and_capped():
    tags = _hashtags("Science", ["#Space", "space", "Moon"])
    lowered = [t.lower() for t in tags]
    assert len(lowered) == len(set(lowered))
    assert len(tags) <= 12
