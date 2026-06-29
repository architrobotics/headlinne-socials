"""Background image quality helpers: choosing the best feed image, fetching a
higher-resolution article hero when needed, and rewriting URLs to larger
variants. Pure-logic tests; the one network call is patched by hand so the
suite runs with or without pytest."""

from __future__ import annotations

from contextlib import contextmanager

import headlinne.news.images as images
from headlinne.news.images import _url_width_hint, best_story_image, image_from_entry
from headlinne.render.carousel import _upgrade_candidates
from headlinne.models import Story


@contextmanager
def _og_returns(value):
    """Temporarily replace the network og:image lookup with a stub."""
    calls = {"n": 0}

    def stub(url):
        calls["n"] += 1
        return value

    original = images._og_image
    images._og_image = stub
    try:
        yield calls
    finally:
        images._og_image = original


def _story(image_url=None, url="https://news.example.com/article"):
    return Story(title="t", summary="s", url=url, category="Geopolitics",
                 source="BBC World", tier=1.4, published_iso="", image_url=image_url)


# --- URL upgrade ladder ----------------------------------------------------- #
def test_candidates_strip_wordpress_suffix_first():
    cands = _upgrade_candidates("https://site.com/wp/photo-1024x576.jpg")
    assert cands[0] == "https://site.com/wp/photo.jpg"


def test_candidates_ladder_bbc_widths_largest_first():
    cands = _upgrade_candidates("https://ichef.bbci.co.uk/news/240/cpsprodpb/x.jpg")
    assert "/2048/cpsprodpb/" in cands[0]
    assert "/1536/cpsprodpb/" in cands[1]
    assert "/1024/cpsprodpb/" in cands[2]


def test_candidates_bump_width_query():
    cands = _upgrade_candidates("https://i.guim.co.uk/img/x?width=300&q=85")
    assert cands[0] == "https://i.guim.co.uk/img/x?width=2048&q=85"


def test_candidates_empty_for_plain_url():
    assert _upgrade_candidates("https://cdn.com/full/image.jpg") == []
    assert _upgrade_candidates("") == []


# --- width hint parsing ----------------------------------------------------- #
def test_width_hint_reads_common_patterns():
    assert _url_width_hint("https://s/a-1024x576.jpg") == 1024
    assert _url_width_hint("https://ichef.bbci.co.uk/news/240/cpsprodpb/x.jpg") == 240
    assert _url_width_hint("https://s/x?width=1200") == 1200
    assert _url_width_hint("https://s/x?resize=320,180") == 320
    assert _url_width_hint("https://s/plain.jpg") == 0
    assert _url_width_hint(None) == 0


# --- best_story_image ------------------------------------------------------- #
def test_keeps_large_feed_image_without_fetching():
    with _og_returns("https://should.not/be-used.jpg") as calls:
        s = _story(image_url="https://i.guim.co.uk/img/x?width=1200")
        assert best_story_image(s) == "https://i.guim.co.uk/img/x?width=1200"
        assert calls["n"] == 0  # large enough, no hero fetch


def test_fetches_hero_for_small_thumbnail():
    with _og_returns("https://ichef.bbci.co.uk/news/1024/branded/x.jpg"):
        s = _story(image_url="https://ichef.bbci.co.uk/news/240/cpsprodpb/x.jpg")
        assert best_story_image(s) == "https://ichef.bbci.co.uk/news/1024/branded/x.jpg"


def test_uses_hero_when_feed_image_missing():
    with _og_returns("https://cdn.aj.com/hero.jpg"):
        s = _story(image_url=None)
        assert best_story_image(s) == "https://cdn.aj.com/hero.jpg"


def test_falls_back_to_feed_when_no_hero():
    with _og_returns(None):
        url = "https://ichef.bbci.co.uk/news/240/cpsprodpb/x.jpg"
        assert best_story_image(_story(image_url=url)) == url


# --- candidate selection from a feed entry ---------------------------------- #
def test_image_from_entry_prefers_largest_width():
    entry = {
        "media_content": [
            {"url": "https://c.com/small.jpg", "width": "320"},
            {"url": "https://c.com/big.jpg", "width": "1200"},
        ],
        "media_thumbnail": [{"url": "https://c.com/thumb.jpg", "width": "150"}],
    }
    assert image_from_entry(entry) == "https://c.com/big.jpg"


def test_image_from_entry_prefers_full_image_over_thumbnail():
    entry = {
        "media_content": [{"url": "https://c.com/main.jpg"}],
        "media_thumbnail": [{"url": "https://c.com/thumb.jpg", "width": "100"}],
    }
    assert image_from_entry(entry) == "https://c.com/main.jpg"


def test_image_from_entry_none_when_empty():
    assert image_from_entry({"summary": "no images here"}) is None
