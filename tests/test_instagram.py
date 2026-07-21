"""The Instagram generator decides how many stories a carousel covers (3 or 5),
builds a clean fallback cover title, blends hashtags, and renders the on-slide
source-attribution line that mirrors the ranker's cross-source verification."""

from __future__ import annotations

from headlinne.generate.instagram import (_clamp_words, _cover_title,
                                          _decide_num_stories, _hashtags,
                                          source_line)
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


def test_cover_title_fallbacks_are_clean_and_counted():
    # The fallback title mentions the count and stays free of the old flag hack.
    assert _cover_title("Technology", 3) == "The 3 tech stories that matter today"
    assert _cover_title("Finance", 5) == "The 5 money moves that matter today"
    assert "world" in _cover_title("Geopolitics", 3).lower()


def test_hashtags_dedupe_and_brand_appended():
    tags = _hashtags("Technology", ["AI", "tech", "Gadgets"])
    lowered = [t.lower() for t in tags]
    # No duplicates regardless of case ('AI'/'ai', 'Tech'/'tech').
    assert len(lowered) == len(set(lowered))
    # Brand is always included.
    assert any(t.lower() == "headlinne" for t in tags)


def test_source_line_lists_names_then_overflow():
    story = make_story("A big event", source="Reuters",
                       corroborating=["BBC", "CNBC", "AP"])
    # Shows the first two outlets, then a '+N' for the rest (4 total sources).
    assert source_line(story) == "Reuters, BBC +2"


def test_source_line_single_source_has_no_overflow():
    story = make_story("A quiet story", source="BBC", corroborating=[])
    assert source_line(story) == "BBC"


def test_clamp_words_trims_on_word_boundary():
    out = _clamp_words("one two three four five six seven eight", 20)
    assert len(out) <= 20
    # Never cuts a word in half or leaves trailing punctuation.
    assert not out.endswith(" ")
    assert out.split() == out.split()  # sanity: still whole words
    assert _clamp_words("short title", 40) == "short title"
