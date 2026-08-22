"""Ranking is how we verify stories across sources and decide what leads.
These tests check that near-duplicate headlines merge into one corroborated
event, that more independent sources raise a story's score, and that category
strength is computed correctly."""

from __future__ import annotations

from headlinne.news.ranking import (_cluster, _low_value_penalty, _merge, _score,
                                     rank, strongest_categories)
from tests.helpers import make_story


def test_near_duplicate_headlines_cluster_together():
    stories = [
        make_story("Acme unveils powerful widget gadget", source="BBC"),
        make_story("Acme unveils a powerful widget gadget today", source="Reuters"),
        make_story("Federal Reserve holds interest rates steady", source="CNBC",
                   category="Finance"),
    ]
    clusters = _cluster(stories)
    sizes = sorted(len(c) for c in clusters)
    # The two Acme headlines merge; the Fed story stands alone.
    assert sizes == [1, 2]


def test_merge_collects_corroborating_sources():
    members = [
        make_story("Acme unveils powerful widget gadget", source="BBC", tier=1.4),
        make_story("Acme unveils powerful widget gadget", source="Reuters", tier=1.2),
        make_story("Acme unveils powerful widget gadget", source="The Verge", tier=1.1),
    ]
    merged = _merge(members)
    assert merged.source_count == 3
    # Representative is the highest-tier source.
    assert merged.source == "BBC"
    assert "Reuters" in merged.corroborating_sources
    assert "The Verge" in merged.corroborating_sources


def test_more_sources_means_higher_score():
    well_sourced = [
        make_story("Acme unveils widget gadget", source=s)
        for s in ("BBC", "Reuters", "CNBC")
    ]
    lone = [make_story("Beta reveals doohickey contraption", source="BBC")]
    digest = rank(well_sourced + lone)
    tech = digest.by_category["Technology"]
    by_title = {s.title: s for s in tech}
    strong = by_title["Acme unveils widget gadget"]
    weak = by_title["Beta reveals doohickey contraption"]
    assert strong.score > weak.score


def test_clustering_reduces_event_count():
    stories = [make_story("Acme unveils widget gadget", source=s)
               for s in ("BBC", "Reuters", "CNBC", "Wired")]
    digest = rank(stories)
    # Four reports of one event collapse to a single ranked story.
    assert len(digest.by_category["Technology"]) == 1


def test_strongest_categories_orders_by_weight_and_skips_empty():
    stories = [
        # Technology: three corroborated events -> heavy weight.
        *[make_story("Acme unveils widget gadget", source=s)
          for s in ("BBC", "Reuters", "CNBC")],
        make_story("Gamma debuts shiny appliance machine", source="Wired"),
        make_story("Delta ships clever software platform", source="The Verge"),
        # Finance: one lighter event.
        make_story("Small bank reports modest quarterly figures",
                   category="Finance", source="MarketWatch", tier=0.9),
    ]
    digest = rank(stories)
    top2 = strongest_categories(digest, 2)
    assert top2[0] == "Technology"
    assert "Finance" in top2
    # Geopolitics had no stories, so it must not appear.
    assert "Geopolitics" not in top2


def test_rank_handles_empty_input():
    digest = rank([])
    assert digest.dominant_category in ("Technology", "Finance", "Geopolitics")
    assert all(v == [] for v in digest.by_category.values())


def test_low_value_content_is_penalised():
    # An opinion/live-blog headline scores lower than a straight news headline
    # about an equally-sourced event, so genuine news leads the carousel.
    hard_news = make_story("Central bank raises interest rates", source="BBC", tier=1.4)
    soft = make_story("Opinion: live updates on why the rate move is wrong",
                      source="BBC", tier=1.4)
    assert _score(hard_news) > _score(soft)
    assert _low_value_penalty("opinion: live updates here") > 0
    assert _low_value_penalty("a normal news headline") == 0


def test_breadth_bonus_favours_well_verified_big_stories():
    # Same three-source coverage, but the reputable-outlet version earns the
    # breadth bonus and ranks above a lower-tier trio.
    trusted = [make_story("A major treaty is signed today", source=s, tier=1.4,
                          category="Geopolitics")
               for s in ("BBC", "Reuters", "AP")]
    scrappy = [make_story("A minor local dispute continues", source=s, tier=0.9,
                          category="Geopolitics")
               for s in ("BlogA", "BlogB", "BlogC")]
    digest = rank(trusted + scrappy)
    geo = digest.by_category["Geopolitics"]
    assert geo[0].title == "A major treaty is signed today"


# --------------------------------------------------------------------------- #
# Topical fit
#
# HIGH_INTEREST_KEYWORDS answers "is this our beat", never "is this
# interesting". Both of the tests below are regressions from a real run.
# --------------------------------------------------------------------------- #
def test_the_topic_lexicon_matches_on_word_boundaries():
    """`k in text` counted "said" as an AI story.

    Measured on one real day of 380 stories: "ai" matched as a substring in 46%
    of them while 8% were actually about AI, and the term carried 29% of the
    ranking's whole variance. "war" matched warning, warming, toward and
    software; "oil" matched boiling and spoiled.
    """
    from headlinne.news.ranking import _TOPIC_RX
    from headlinne.news._lexicon import distinct_hits

    for innocent in ("said", "again", "against", "campaign", "available",
                     "detail", "certain", "remains", "chair", "explain",
                     "toward", "warning", "warming", "award", "software",
                     "boiling", "spoiled", "recoil"):
        assert distinct_hits(innocent, _TOPIC_RX) == 0, innocent

    for genuine in ("AI", "an AI model", "the war in Ukraine",
                    "oil prices", "a nuclear reactor", "the election"):
        assert distinct_hits(genuine, _TOPIC_RX) > 0, genuine


def test_the_topic_lexicon_never_rewards_what_interest_penalises():
    """Both lexicons are editorial judgement written down, and they used to
    disagree. earnings, stocks, ipo, merger, acquisition, summit and central
    bank sat in the topic list while interest._PAROCHIAL docked them, and the
    topic bonus won because it could add more than the parochial term could
    ever take away. That is how an earnings print outranked a discovery in a
    system built specifically not to do that."""
    from headlinne.config import HIGH_INTEREST_KEYWORDS
    from headlinne.news.interest import _PAROCHIAL

    clash = {t.rstrip("*") for t in HIGH_INTEREST_KEYWORDS} & {
        t.rstrip("*") for t in _PAROCHIAL}
    assert not clash, f"topic list rewards what interest penalises: {sorted(clash)}"


def test_topical_fit_cannot_outweigh_the_interest_score():
    """A tiebreaker, sized like one. The two stories below are equally on-beat
    in vocabulary and are not equally worth reading."""
    from headlinne.news.ranking import _TOPIC_CAP, _TOPIC_WEIGHT
    from headlinne.news.interest import _W_CONCRETE, _W_NOVELTY

    most_topic_can_buy = _TOPIC_WEIGHT * _TOPIC_CAP
    one_strong_interest_term = min(_W_CONCRETE, _W_NOVELTY)
    assert most_topic_can_buy < one_strong_interest_term, (
        f"topical fit is worth {most_topic_can_buy}, which can overturn a "
        f"{one_strong_interest_term}-weight interest term")
