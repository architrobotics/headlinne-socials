"""De-duplication keeps the feed fresh across days. These tests check that an
already-used story or near-identical post text is detected, that distinct
content passes, and that the rolling window prunes old days."""

from __future__ import annotations

from datetime import date

from headlinne.quality.dedup import History


def _history_with(urls=None, titles=None, texts=None, day="2026-06-27"):
    h = History({})
    h.days[day] = {
        "story_urls": list(urls or []),
        "story_titles": list(titles or []),
        "post_texts": list(texts or []),
    }
    return h


def test_story_seen_by_exact_url():
    h = _history_with(urls=["https://example.com/a"])
    assert h.story_seen("https://example.com/a", "Totally different title here")
    assert not h.story_seen("https://example.com/b", "Totally different title here")


def test_story_seen_by_similar_title():
    h = _history_with(titles=["Acme unveils a powerful new widget gadget today"])
    # Same story, slightly reworded headline -> should be caught.
    assert h.story_seen("", "Acme unveils a powerful new widget gadget")
    # Unrelated headline -> not caught.
    assert not h.story_seen("", "Central bank changes its interest rate policy")


def test_text_repeats_detects_near_duplicate_copy():
    prior = ("Here are the three biggest tech stories you should know about today "
             "and why each one actually matters for you")
    h = _history_with(texts=[prior])
    near = ("Here are the three biggest tech stories you should know about today "
            "and why each one really matters for you")
    assert h.text_repeats(near)
    assert not h.text_repeats("A completely unrelated sentence about finance markets.")


def test_record_then_query_roundtrip():
    h = History({})
    today = date(2026, 6, 28)
    h.record(today, story_urls=["https://example.com/x"],
             story_titles=["Some headline about a thing"],
             post_texts=["A post body that we have now used once"])
    assert h.story_seen("https://example.com/x", "unrelated")
    assert today.isoformat() in h.days


def test_prune_drops_old_days():
    h = History({})
    h.days["2026-06-01"] = {"story_urls": [], "story_titles": [], "post_texts": []}
    h.days["2026-06-27"] = {"story_urls": [], "story_titles": [], "post_texts": []}
    h.prune(date(2026, 6, 28))  # window is 10 days
    assert "2026-06-01" not in h.days     # 27 days old -> dropped
    assert "2026-06-27" in h.days         # 1 day old -> kept
