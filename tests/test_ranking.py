"""Ranking is how we verify stories across sources and decide what leads.
These tests check that near-duplicate headlines merge into one corroborated
event, that more independent sources raise a story's score, and that category
strength is computed correctly."""

from __future__ import annotations

from headlinne.news.ranking import _cluster, _merge, rank, strongest_categories
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
