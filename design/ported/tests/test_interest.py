"""Does the ranker prefer a story a person would actually read?

The regression these guard against is the one the old weights had: cross-source
count was the heaviest term, so the highest-scoring story was always the most
widely attended one. On live feeds that produced a rate decision above a rocket
hitting the Moon, and an X-Files director's cut in the top eight twice.
"""

from __future__ import annotations

from headlinne.models import Story
from headlinne.news import interest as I
from headlinne.news.ranking import rank


def _story(title, summary="", category="Technology", tier=1.2, source="Example",
           image=None):
    return Story(
        title=title, summary=summary, url="https://example.com/" + title[:12],
        category=category, source=source, tier=tier,
        published_iso="2026-08-15T09:00:00+00:00", image_url=image)


def _covered_by(title, outlets, **kw):
    """The same event as filed by several outlets, so the ranker clusters it.

    Corroboration cannot be faked on a single Story: _merge() rebuilds it from
    the distinct source names of a real cluster, which is what makes
    Story.verified mean anything.
    """
    return [_story(title, source=o, **kw) for o in outlets]


MOON = "A SpaceX rocket crashed into the Moon at 8,700 kilometres per hour"
RATES = "Bank holds interest rates for a fourth consecutive meeting"


def test_an_event_outscores_a_process():
    assert I.interest(MOON) > I.interest(RATES)


def test_procedural_language_is_penalised():
    plain = I.interest("Regulator approved the merger")
    proc = I.interest("Regulator meets to discuss whether it could approve the merger")
    assert plain > proc


def test_universal_beats_parochial():
    assert I.interest("New research explains why the human brain forgets") > \
           I.interest("Borough council committee weighs quarterly earnings report")


def test_a_photograph_counts_for_something():
    assert I.interest(MOON, has_image=True) > I.interest(MOON, has_image=False)


def test_concrete_numbers_beat_abstractions():
    assert I.interest("The crater is 29 metres wide") > \
           I.interest("Officials described the outcome as significant")


def test_sensitive_stories_are_flagged_not_scored_down():
    """They must publish - they just must not be dressed up as delightful."""
    grim = "At least 44 dead after an overcrowded ferry capsized"
    assert I.is_sensitive(grim)
    assert not I.is_sensitive(MOON)
    assert I.interest(grim) > 0      # still a real story, still rankable


def test_wide_coverage_no_longer_buries_an_interesting_story():
    """The exact failure the old weights had, as a test."""
    digest = rank(
        _covered_by(RATES, ["Reuters", "BBC", "FT", "AP", "Sky", "CNBC"],
                    summary="The committee voted to hold.", category="Finance",
                    tier=1.4)
        + _covered_by(MOON, ["Space.com", "New Scientist"],
                      summary="Four tonnes, near Einstein Crater.",
                      image="https://example.com/x.jpg"))
    top = max((s for v in digest.by_category.values() for s in v),
              key=lambda s: s.score)
    assert MOON in top.title, "the widely-covered process story won again"


def test_ranking_sets_the_verification_and_sensitivity_flags():
    digest = rank(
        _covered_by(MOON, ["Space.com", "New Scientist", "Reuters"])
        + [_story("Two dead in a factory fire", category="Geopolitics")])
    everything = [s for v in digest.by_category.values() for s in v]
    by_title = {s.title: s for s in everything}
    assert by_title[MOON].verified is True
    assert by_title[MOON].sensitive is False
    fire = by_title["Two dead in a factory fire"]
    assert fire.verified is False, "one source is not verification"
    assert fire.sensitive is True


def test_explainers_are_no_longer_treated_as_low_value():
    """They are the evening reel's entire genre."""
    from headlinne.news.ranking import _LOW_VALUE_MARKERS
    assert "explainer" not in _LOW_VALUE_MARKERS
    assert "how to" not in _LOW_VALUE_MARKERS
