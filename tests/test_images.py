"""Background image quality helpers: choosing the best feed image and rewriting
its URL to a higher-resolution variant. These are pure-string/logic tests."""

from __future__ import annotations

from headlinne.news.images import image_from_entry
from headlinne.render.carousel import _upgrade_image_url


def test_upgrade_strips_wordpress_dimension_suffix():
    out = _upgrade_image_url("https://site.com/wp/photo-1024x576.jpg")
    assert out == "https://site.com/wp/photo.jpg"
    # Keeps any query string intact.
    out2 = _upgrade_image_url("https://site.com/a-300x200.jpg?x=1")
    assert out2 == "https://site.com/a.jpg?x=1"


def test_upgrade_bumps_bbc_ichef_width():
    out = _upgrade_image_url("https://ichef.bbci.co.uk/news/240/cpsprodpb/abc/x.jpg")
    assert "/1600/cpsprodpb/" in out
    # An already-large width is left alone.
    big = "https://ichef.bbci.co.uk/news/2048/cpsprodpb/abc/x.jpg"
    assert _upgrade_image_url(big) == big


def test_upgrade_bumps_width_query_params():
    assert _upgrade_image_url("https://i.guim.co.uk/img/x?width=300&quality=85") \
        == "https://i.guim.co.uk/img/x?width=1600&quality=85"
    assert _upgrade_image_url("https://cdn.com/x?w=140&h=90") \
        == "https://cdn.com/x?w=1600&h=90"
    # Already large stays put.
    assert _upgrade_image_url("https://cdn.com/x?width=2000") \
        == "https://cdn.com/x?width=2000"


def test_upgrade_scales_resize_pair_keeping_ratio():
    out = _upgrade_image_url("https://cdn.com/x?resize=320,180")
    assert out == "https://cdn.com/x?resize=1600,900"


def test_upgrade_leaves_plain_urls_untouched():
    plain = "https://cdn.com/full/image.jpg"
    assert _upgrade_image_url(plain) == plain
    assert _upgrade_image_url("") == ""


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
        "media_content": [{"url": "https://c.com/main.jpg"}],   # no width given
        "media_thumbnail": [{"url": "https://c.com/thumb.jpg", "width": "100"}],
    }
    # The full media_content image outranks a tiny thumbnail.
    assert image_from_entry(entry) == "https://c.com/main.jpg"


def test_image_from_entry_none_when_empty():
    assert image_from_entry({"summary": "no images here"}) is None
