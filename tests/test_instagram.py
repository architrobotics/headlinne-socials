"""The Instagram generator decides how many stories a carousel covers (3 or 5)
and builds the cover title. The Geopolitics title must keep the word
'Geopolitics' intact so the renderer can flag-style the 'Geo' part."""

from __future__ import annotations

from headlinne.generate.instagram import _cover_title, _decide_num_stories, _hashtags
from tests.helpers import make_story


def test_decide_num_stories_three_when_deep_stories_weak():
    stories = [make_story(f"Story number {i}", score=s)
               for i, s in enumerate([10.0, 8.0, 6.0, 2.0, 1.0])]
    # Fifth story (1.0) is far below half the top (10.0) -> keep it tight.
    assert _decide_num_stories(stories) == 3


def test_decide_num_stories_five_when_deep_stories_strong():
    stories = [make_story(f"Story number {i}", score=s)
               for i, s in enumerate([10.0, 9.0, 8.0, 7.0, 6.0])]
    # Fifth story (6.0) is well above half the top (10.0) -> five is justified.
    assert _decide_num_stories(stories) == 5


def test_decide_num_stories_handles_few_stories():
    assert _decide_num_stories([make_story("only one")]) == 1
    assert _decide_num_stories([make_story("a"), make_story("b")]) == 2
    # Defensive floor of 1 even if called with nothing (caller already guards).
    assert _decide_num_stories([]) == 1


def test_cover_title_per_category():
    assert _cover_title("Technology", 3) == "Top 3 Things In Tech Today"
    assert _cover_title("Finance", 5) == "Top 5 Finance Stories Today"


def test_geopolitics_cover_title_keeps_geo_word():
    title = _cover_title("Geopolitics", 3)
    # Renderer looks for a leading 'Geo' to apply stars-and-stripes styling.
    assert title.startswith("Top 3 Geo")
    assert "Geopolitics" in title


def test_hashtags_dedupe_and_brand_appended():
    tags = _hashtags("Technology", ["AI", "tech", "Gadgets"])
    lowered = [t.lower() for t in tags]
    # No duplicates regardless of case ('AI'/'ai', 'Tech'/'tech').
    assert len(lowered) == len(set(lowered))
    # Brand is always included.
    assert any(t.lower() == "headlinne" for t in tags)
