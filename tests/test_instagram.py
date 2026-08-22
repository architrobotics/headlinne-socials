"""The daily carousel: what earns it, and how the five slides are assembled."""

from headlinne.generate.instagram import (_hashtags, _slides, agreement_line,
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


def test_corroboration_is_a_preference_and_not_a_floor():
    """A hard three-outlet gate left three candidates in a pool of 380, and not
    one of the twenty most interesting stories was among them. Corroboration is
    rare in this feed set, so a floor does not raise the standard - it just
    hands the format whatever got syndicated."""
    thin = _story("A genuinely remarkable single-source find", score=14.0,
                  outlets=1)
    wire = _story("Third rate cut discussed at summit", score=9.0, outlets=5)
    assert pick_story(_digest([thin, wire])) is thin


def test_a_single_source_story_is_described_honestly_rather_than_refused():
    """The fourth slide is the source strip, and the strip already has a
    SINGLE SOURCE state with its own tone and its own pose. The format does not
    need protecting from a story it can describe accurately."""
    thin = _story("Single-source scoop", score=9.9, outlets=1)
    picked = pick_story(_digest([thin]))
    assert picked is thin
    assert picked.agreement.state == "single"


def test_the_source_bonus_is_bounded_so_a_wire_story_cannot_coast_on_outlets():
    """Every extra outlet past the cap is worth nothing, or the format drifts
    back to picking whatever the most outlets ran."""
    many = _story("Carried by everyone, interesting to nobody", score=8.0,
                  outlets=12)
    good = _story("Carried by two, worth five slides", score=11.0, outlets=2)
    assert pick_story(_digest([many, good])) is good


def test_two_comparable_stories_are_split_by_their_sourcing():
    thin = _story("Comparable, one outlet", score=9.0, outlets=1)
    sourced = _story("Comparable, four outlets", score=9.0, outlets=4)
    assert pick_story(_digest([thin, sourced])) is sourced


def test_a_day_with_no_stories_at_all_skips_the_format():
    assert pick_story(_digest([])) is None


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


# --------------------------------------------------------------------------- #
# One event, one format
# --------------------------------------------------------------------------- #
def test_two_outlets_on_one_event_are_recognised_as_one_event():
    """The real collision: Wired filed it under Technology, Phys.org under
    Science, the URLs differ, and the day put the same discovery on both the
    carousel and the story card."""
    from headlinne.news.ranking import same_event

    a = _story("Astronomers Discover the Existence of a Black Hole Star",
               category="Technology")
    b = _story("Black hole star: Astronomers discover a brand-new type of "
               "astrophysical object", category="Science")
    assert same_event(a, b)


def test_unrelated_stories_are_not_treated_as_one_event():
    from headlinne.news.ranking import same_event

    a = _story("Astronomers Discover the Existence of a Black Hole Star")
    b = _story("Ebola outbreak in Democratic Republic of Congo now deadliest")
    c = _story("Homes near pylons to get money off energy bills")
    assert not same_event(a, b)
    assert not same_event(a, c)
    assert not same_event(b, c)


def test_the_same_event_bar_is_looser_than_the_clustering_bar():
    """Deliberately. A false merge in clustering prints "4 outlets agree" under
    a story four outlets did not agree on. A false positive here costs the day
    its second-best story. The two do not deserve the same caution."""
    from headlinne.news.ranking import SAME_EVENT_SIM, _SIM_THRESHOLD

    assert SAME_EVENT_SIM < _SIM_THRESHOLD


def test_the_carousel_skips_a_story_the_reel_already_took():
    reel_story = _story("Astronomers Discover the Existence of a Black Hole Star",
                        score=12.0, outlets=4)
    same = _story("Black hole star: Astronomers discover a brand-new type of "
                  "astrophysical object", score=11.0, outlets=4)
    other = _story("Homes near pylons to get money off energy bills",
                   score=10.0, outlets=4)
    picked = pick_story(_digest([same, other]), exclude_stories=[reel_story])
    assert picked is other, "the carousel repeated the reel's event"


def test_excluding_by_story_still_honours_the_url_exclusion():
    a = _story("Story A", score=9.0, outlets=4)
    b = _story("Completely different subject matter here", score=8.0, outlets=4)
    assert pick_story(_digest([a, b]), exclude_urls={a.url}) is b
