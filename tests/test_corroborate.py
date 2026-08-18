"""Corroboration: independent voices, syndication, and the agreement arithmetic.

The matching thresholds are calibrated against a real day's corpus, so the tests
that exercise them build a realistically sized one. On a handful of stories every
term looks common and nothing clears the entity-weight bar - which is correct
behaviour, and is itself asserted below.
"""

from headlinne.models import Story
from headlinne.news import corroborate as C

WIRE = ("A Falcon 9 upper stage struck the lunar surface near Einstein Crater on "
        "Tuesday at 8,700 km/h, NASA confirmed. (Reuters)")


def _story(title, source, summary="", tier=1.0):
    return Story(title=title, summary=summary, url=f"http://x/{source}/{title[:12]}",
                 category="Science", source=source, tier=tier,
                 published_iso="2026-08-17T06:00:00+00:00")


def _moon_reports():
    return [
        _story("SpaceX rocket hits the Moon at 8,700 km/h near Einstein Crater",
               "New Scientist",
               "A Falcon 9 upper stage struck the lunar surface near Einstein "
               "Crater on Tuesday at 8,700 km/h, NASA said. Danuri repositioned "
               "to photograph the impact.", 1.2),
        _story("Rocket stage strikes Moon at 8,700 km/h, NASA confirms",
               "Reuters", WIRE, 1.4),
        _story("Rocket stage strikes Moon at 8,700 km/h, NASA confirms",
               "Sky News", WIRE, 1.0),
        _story("Rocket stage strikes Moon at 8,700 km/h, NASA confirms",
               "France 24", WIRE, 1.0),
        _story("Lunar impact near Einstein Crater photographed by Danuri orbiter",
               "Space.com",
               "South Korea's Danuri orbiter photographed the Einstein Crater "
               "impact site. The stage was travelling at 8,690 km/h when it "
               "struck the Moon, NASA said.", 1.0),
        _story("Moon impact near Einstein Crater was far slower, says analyst",
               "Phys.org",
               "An independent analysis puts the Einstein Crater lunar impact "
               "speed at 5,200 km/h, well below the NASA figure.", 1.0),
    ]


def _padded_corpus():
    """A realistic day, so inverse document frequency behaves as it does live."""
    reports = _moon_reports()
    filler = [_story(f"Routine development number {i} in an unrelated sector",
                     f"Outlet{i}", f"Wire copy about unrelated matter {i}.")
              for i in range(240)]
    return reports, reports + filler


def test_one_agency_story_carried_by_three_outlets_is_one_voice():
    groups = C.collapse_syndication(_moon_reports())
    wire_group = next(g for g in groups if any(s.source == "Reuters" for s in g))
    assert {s.source for s in wire_group} == {"Reuters", "Sky News", "France 24"}
    # The highest-tier carrier represents the group on the source strip.
    assert wire_group[0].source == "Reuters"


def test_independent_reports_of_one_event_stay_separate():
    groups = C.collapse_syndication(_moon_reports())
    singles = {g[0].source for g in groups if len(g) == 1}
    assert {"New Scientist", "Space.com", "Phys.org"} <= singles


def test_an_agency_credit_is_detected_in_the_copy():
    assert C.wire_credit(_story("x", "Sky News", WIRE)) == "reuters"
    assert C.wire_credit(_story("x", "Space.com", "Our correspondent reports.")) is None


def test_corroboration_counts_independent_voices_not_mastheads():
    reports, corpus = _padded_corpus()
    others = C.corroborate(reports[0], corpus)
    names = {o.source for o in others}
    assert "Reuters" in names
    # Sky News and France 24 are the same copy as Reuters and must not appear.
    assert not names & {"Sky News", "France 24"}


def test_the_denominator_is_the_outlets_that_reported_not_the_corpus():
    reports, corpus = _padded_corpus()
    story = reports[0]
    C.attach([story], corpus)
    assert story.agreement.reported == 4, story.agreement.outlets
    assert len(corpus) > 240, "the corpus is large and must not reach the strip"


def test_a_rounded_restatement_agrees_and_a_different_figure_conflicts():
    reports, corpus = _padded_corpus()
    story = reports[0]
    C.attach([story], corpus)
    a = story.agreement
    assert a.claim == "8,700 km/h"
    assert a.agree == 3           # New Scientist, Reuters, Space.com (8,690)
    assert a.conflict == 1        # Phys.org (5,200)
    assert [c.outlet for c in a.conflicts] == ["Phys.org"]
    assert a.label() == "3 of 4 outlets agree"
    assert a.state == "disputed"
    assert story.verified


def test_a_thin_corpus_corroborates_nothing_rather_than_guessing():
    # With six stories every entity looks common, so the weight gate refuses.
    # Refusing is the correct failure: a false source strip is worse than a thin
    # one.
    reports = _moon_reports()
    assert C.corroborate(reports[0], reports) == []


def test_a_roundup_never_vouches_for_anything():
    assert C.is_roundup("In tonight's edition: six stories from around the world")
    assert C.is_roundup("Ebola cases rise", "Also in the bulletin: markets, sport")
    assert not C.is_roundup("Ebola cases rise in eastern Congo")


def test_a_story_with_no_figure_agrees_on_the_event_itself():
    reports, corpus = _padded_corpus()
    story = _story("Danuri orbiter repositions over Einstein Crater on the Moon",
                   "New Scientist",
                   "The Danuri orbiter moved to photograph the Einstein Crater "
                   "lunar impact site, NASA said.", 1.2)
    C.attach([story], [story] + corpus[1:])
    a = story.agreement
    assert a.claim == ""
    assert a.agree == a.reported, "with nothing quantified, coverage is the claim"
    assert a.conflict == 0
