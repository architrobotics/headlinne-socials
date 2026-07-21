"""Smoke tests for the carousel renderer.

These render a full carousel offline (no network: every slide uses the designed
brand fallback background) and assert the pipeline produces correctly-sized,
non-empty PNGs for each slide role. They guard against the whole render path
crashing, which the pure-logic tests cannot catch.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from headlinne.config import SLIDE_H, SLIDE_W
from headlinne.models import InstagramCarousel, Slide
from headlinne.render import theme
from headlinne.render.carousel import render_carousel


def _carousel(category: str = "Technology") -> InstagramCarousel:
    slides = [
        Slide(role="cover", headline="A big shift you should know about",
              subtitle="Three stories that change the week ahead.", image_url=None),
        Slide(role="story", headline="First thing happened today",
              explanation="Here is what happened. Here is why it matters to you.",
              sources="Reuters, BBC +2", index=1, image_url=None),
        Slide(role="story", headline="Second thing happened too",
              explanation="A short, clear explanation of the second story.",
              sources="AP", index=2, image_url=None),
        Slide(role="cta", headline="That's your brief for today.",
              subtitle="Personalised news, minus the noise."),
    ]
    return InstagramCarousel(
        slot="instagram_1", category=category, num_slides=len(slides),
        title="A big shift you should know about", slides=slides,
        caption="Caption.", hashtags=["Tech"],
        scheduled_time="2026-07-21T16:00:00+05:30",
    )


def test_render_produces_correctly_sized_pngs():
    from PIL import Image

    carousel = _carousel()
    with tempfile.TemporaryDirectory() as tmp:
        paths = render_carousel(carousel, Path(tmp))
        assert len(paths) == len(carousel.slides)
        for path in paths:
            assert path.exists()
            # A real drawn slide is far bigger than an empty canvas would compress to.
            assert path.stat().st_size > 8_000
            with Image.open(path) as img:
                assert img.size == (SLIDE_W, SLIDE_H)
                assert img.mode == "RGB"


def test_render_sets_image_file_on_each_slide():
    carousel = _carousel()
    with tempfile.TemporaryDirectory() as tmp:
        render_carousel(carousel, Path(tmp))
        for slide in carousel.slides:
            assert slide.image_file and slide.image_file.endswith(".png")


def test_render_runs_for_every_category():
    # Each category has its own accent; all must render without error.
    for category in ("Technology", "Finance", "Geopolitics"):
        with tempfile.TemporaryDirectory() as tmp:
            paths = render_carousel(_carousel(category), Path(tmp))
            assert len(paths) == 4


def test_theme_accent_and_pill_helpers():
    for category in ("Technology", "Finance", "Geopolitics"):
        accent = theme.accent_for(category)
        assert isinstance(accent, tuple) and len(accent) == 3
        assert all(0 <= c <= 255 for c in accent)
        assert theme.pill_label(category).isupper()
