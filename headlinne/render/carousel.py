"""Render the daily carousel to PNG slides.

One carousel, one story, five slides doing five different jobs:

    cover    what happened - Pip, a bubble, the headline, the receipt
    scale    how big - one number set enormous, and what it is comparable to
    twist    the thing you did not know, or the image that proves it
    sources  the receipt in full, with every outlet named
    cta      the domain, as the loudest object on the slide

That shape is the whole change. The old carousel was a listicle - a cover, then
three or five unrelated stories under identical layouts, then a sign-off - and a
list has no reason to be swiped past its second entry. An argument does: each
slide answers the question the previous one raised, which is what carries a
reader to the end and what makes the last slide worth putting a call to action
on.

Backgrounds are paper. Photography appears as a tilted, taped plate rather than
as a full-bleed image under a scrim, because a plate reads as an object someone
placed and a scrim reads as a stock template. render/plate.py owns the ladder
that decides what goes in the frame when there is no usable photograph.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageDraw

from ..config import SLIDE_H, SLIDE_W, WEBSITE
from ..logging_setup import get_logger
from ..models import InstagramCarousel, Slide
from . import fonts, plate as plate_mod, receipt as receipt_mod, theme

log = get_logger("render.carousel")

ImageLoader = Callable[[Optional[str]], Optional[Image.Image]]

MARGIN = theme.MARGIN

# The vertical grid, transcribed from design/prototypes/formats.py.
PIP_Y = 196
BUBBLE_X = MARGIN + 350
BUBBLE_Y = 236
KICKER_Y = 606
HEADLINE_Y = 664
HEADLINE_LH = 96
RECEIPT_FROM_BOTTOM = 322

PLATE_W, PLATE_H = 560, 380


# --------------------------------------------------------------------------- #
# Image loading (unchanged behaviour: upgrade thumbnails, cover-fit, sharpen)
# --------------------------------------------------------------------------- #
_UPGRADE_WIDTHS = (2048, 1536, 1024)


def _upgrade_candidates(url: str) -> list[str]:
    """Ordered higher-resolution variants of a thumbnail URL, largest first."""
    if not url:
        return []
    candidates: list[str] = []
    stripped = re.sub(r"-\d{2,4}x\d{2,4}(?=\.(?:jpg|jpeg|png|webp)\b)", "", url,
                      flags=re.I)
    if stripped != url:
        candidates.append(stripped)

    for target in _UPGRADE_WIDTHS:
        u = url
        u = re.sub(r"(/)(\d{2,4})(/cpsprodpb/)",
                   lambda m, t=target: m.group(1) + str(max(int(m.group(2)), t)) + m.group(3), u)
        u = re.sub(r"(?i)([?&](?:width|w|maxwidth)=)(\d{2,4})",
                   lambda m, t=target: m.group(1) + str(max(int(m.group(2)), t)), u)

        def _pair(m, t=target):
            w_, h_ = int(m.group(2)), int(m.group(3))
            if w_ >= t:
                return m.group(0)
            return f"{m.group(1)}{t},{int(h_ * t / w_)}"

        u = re.sub(r"(?i)([?&](?:resize|fit)=)(\d{2,4}),(\d{2,4})", _pair, u)
        if u != url and u not in candidates:
            candidates.append(u)
    return candidates


def _fetch_image(url: str) -> Optional[Image.Image]:
    try:
        if url.startswith("http://") or url.startswith("https://"):
            import requests  # local import so tests do not need network

            resp = requests.get(url, timeout=12,
                                headers={"User-Agent": "Headlinne/1.0"})
            resp.raise_for_status()
            return Image.open(BytesIO(resp.content)).convert("RGBA")
        path = Path(url)
        if path.exists():
            return Image.open(path).convert("RGBA")
    except Exception as exc:  # pragma: no cover - network/IO best-effort
        log.warning("Background load failed for %s: %s", str(url)[:80], exc)
    return None


def default_image_loader(src: Optional[str]) -> Optional[Image.Image]:
    """Load a background from an http(s) URL or a local file path."""
    if not src:
        return None
    if src.startswith("http://") or src.startswith("https://"):
        for candidate in _upgrade_candidates(src):
            img = _fetch_image(candidate)
            if img is not None:
                return img
        return _fetch_image(src)
    return _fetch_image(src)


# --------------------------------------------------------------------------- #
# Shared slide chrome
# --------------------------------------------------------------------------- #
def _dateline(when: str) -> str:
    try:
        d = datetime.fromisoformat(when).date()
    except (ValueError, TypeError):
        d = date.today()
    return d.strftime("%a %-d %b").upper() if hasattr(d, "strftime") else ""


def _dateline_safe(when: str) -> str:
    """`%-d` is not portable to Windows, so the day is trimmed by hand."""
    try:
        d = datetime.fromisoformat(when).date()
    except (ValueError, TypeError):
        d = date.today()
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}".upper()


def _open_slide(carousel: InstagramCarousel, tone) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    canvas = theme.paper(SLIDE_W, SLIDE_H)
    draw = ImageDraw.Draw(canvas)
    theme.draw_masthead(canvas, draw, tone=tone,
                        date_text=_dateline_safe(carousel.scheduled_time))
    return canvas, draw


def _close_slide(canvas: Image.Image, draw: ImageDraw.ImageDraw) -> Image.Image:
    theme.draw_footer(canvas, draw)
    return canvas


def _headline(draw: ImageDraw.ImageDraw, text: str, *, y: int,
              start: int = 84, min_size: int = 56, max_lines: int = 4) -> int:
    """Set a headline as large as it can be without exceeding `max_lines`.

    The design system says a headline needing more than three lines routes to
    the carousel rather than shrinking. This *is* the carousel, so four is the
    floor here and the type still never drops below `min_size`.
    """
    size = start
    while size > min_size:
        font = fonts.title_font(size, 800)
        lines = fonts.wrap_text(font, text, SLIDE_W - 2 * MARGIN)
        if len(lines) <= max_lines:
            break
        size -= 4
    font = fonts.title_font(size, 800)
    lines = fonts.wrap_text(font, text, SLIDE_W - 2 * MARGIN)
    lh = int(size * 1.14)
    for line in lines:
        draw.text((MARGIN, y), line, font=font,
                  fill=theme.hex_to_rgb(theme.TEXT_PRIMARY))
        y += lh
    return y


def _body(draw: ImageDraw.ImageDraw, text: str, *, y: int, size: int = 42,
          weight: int = 500, fill=None) -> int:
    if not text:
        return y
    font = fonts.body_font(size, weight)
    lh = int(size * 1.3)
    for line in fonts.wrap_text(font, text, SLIDE_W - 2 * MARGIN):
        draw.text((MARGIN, y), line, font=font,
                  fill=fill or theme.hex_to_rgb(theme.TEXT_SECONDARY))
        y += lh
    return y


def _pip_and_bubble(canvas: Image.Image, draw: ImageDraw.ImageDraw, *,
                    pose: str | None, say: str, scale: int = 15,
                    y: int = PIP_Y) -> None:
    """Pip with an optional bubble. Draws nothing at all when pose is None,
    which is how a sensitive story loses the mascot."""
    if not pose:
        return
    w, h = theme.draw_pip(canvas, pose, x=MARGIN - 30, y=y, scale=scale)
    if say:
        theme.draw_bubble(canvas, draw, say, x=BUBBLE_X, y=y + 40,
                          max_w=SLIDE_W - BUBBLE_X - MARGIN, tail="left")


# --------------------------------------------------------------------------- #
# The five slides
# --------------------------------------------------------------------------- #
def _render_cover(slide: Slide, carousel: InstagramCarousel, story, tone,
                  loader: ImageLoader) -> Image.Image:
    canvas, draw = _open_slide(carousel, tone)
    _pip_and_bubble(canvas, draw, pose=slide.pose, say=slide.say, scale=15)

    y = theme.draw_kicker(draw, slide.kicker or carousel.category,
                          x=MARGIN, y=KICKER_Y, tone=tone)
    y = _headline(draw, slide.headline, y=HEADLINE_Y, start=92, max_lines=3)
    _body(draw, slide.subtitle, y=y + 18)

    if story is not None:
        theme.draw_receipt(canvas, draw, story, x=MARGIN,
                           y=SLIDE_H - RECEIPT_FROM_BOTTOM, names=False)
    return _close_slide(canvas, draw)


def _render_scale(slide: Slide, carousel: InstagramCarousel, story, tone,
                  loader: ImageLoader) -> Image.Image:
    """One number, set enormous, and what it is comparable to.

    A figure a reader can picture is the single most screenshot-able thing a
    news account produces, which is why it gets a slide of its own rather than a
    clause inside a paragraph.
    """
    canvas, draw = _open_slide(carousel, tone)
    theme.draw_kicker(draw, slide.kicker or "HOW BIG", x=MARGIN, y=220, tone=tone)

    figure = slide.figure or ""
    unit = slide.unit or ""
    if figure:
        big = fonts.title_font(280, 800)
        draw.text((MARGIN, 274), figure, font=big,
                  fill=theme.hex_to_rgb(theme.TEXT_PRIMARY))
        if unit:
            width = fonts.text_width(big, figure)
            draw.text((MARGIN + width + 40, 420), unit,
                      font=fonts.title_font(64, 700),
                      fill=theme.hex_to_rgb(theme.TEXT_PRIMARY))

    y = _body(draw, slide.explanation, y=620, size=46)

    plate_img, rung = plate_mod.for_story(story, loader, width=PLATE_W,
                                          height=PLATE_H) if story else (None, "none")
    if plate_img is not None:
        px = SLIDE_W - MARGIN - plate_img.width
        py = min(SLIDE_H - RECEIPT_FROM_BOTTOM - plate_img.height - 40, y + 40)
        canvas.alpha_composite(plate_img, (max(MARGIN, px), max(y + 20, py)))
    elif slide.say and slide.pose:
        _pip_and_bubble(canvas, draw, pose=slide.pose, say=slide.say,
                        scale=12, y=SLIDE_H - 620)
    return _close_slide(canvas, draw)


def _render_twist(slide: Slide, carousel: InstagramCarousel, story, tone,
                  loader: ImageLoader) -> Image.Image:
    """The thing a reader did not know. This is the slide that earns the share."""
    canvas, draw = _open_slide(carousel, tone)
    _pip_and_bubble(canvas, draw, pose=slide.pose, say=slide.say, scale=15)

    theme.draw_kicker(draw, slide.kicker or "WHAT YOU DID NOT KNOW",
                      x=MARGIN, y=610, tone=tone)
    y = _headline(draw, slide.headline, y=668, start=78, max_lines=4)
    _body(draw, slide.explanation, y=max(y + 24, SLIDE_H - 400), size=38)
    return _close_slide(canvas, draw)


def _render_sources(slide: Slide, carousel: InstagramCarousel, story, tone,
                    loader: ImageLoader) -> Image.Image:
    """The receipt, in full. The slide that makes the argument for the product."""
    canvas, draw = _open_slide(carousel, tone)
    _pip_and_bubble(canvas, draw, pose=slide.pose or "verified",
                    say=slide.say, scale=16, y=210)

    theme.draw_kicker(draw, slide.kicker or "SOURCES", x=MARGIN, y=660, tone=tone)
    if story is not None:
        y = theme.draw_receipt(canvas, draw, story, x=MARGIN, y=720,
                               label_size=34, name_size=30)
    else:
        y = 800
    _body(draw, slide.explanation or
          "Headlinne reads every outlet covering a story and shows you where "
          "they agree, and where they do not.", y=max(y + 40, 900), size=40)
    return _close_slide(canvas, draw)


def _render_cta(slide: Slide, carousel: InstagramCarousel, story, tone,
                loader: ImageLoader) -> Image.Image:
    """Pip asks; the domain is the loudest thing on the slide."""
    canvas, draw = _open_slide(carousel, tone)
    _pip_and_bubble(canvas, draw, pose=slide.pose or "carry",
                    say=slide.say or "Come and read it.", scale=16, y=236)

    theme.draw_kicker(draw, slide.kicker or "READ THE FULL STORY",
                      x=MARGIN, y=700, tone=tone)
    y = _headline(draw, WEBSITE.lower(), y=754, start=104, max_lines=1)
    _body(draw, slide.subtitle or
          "Every source on this story, side by side. Free to read, no account "
          "needed.", y=y + 20, size=40)
    if story is not None:
        theme.draw_receipt(canvas, draw, story, x=MARGIN,
                           y=SLIDE_H - RECEIPT_FROM_BOTTOM, names=False)
    return _close_slide(canvas, draw)


_RENDERERS = {
    "cover": _render_cover,
    "scale": _render_scale,
    "twist": _render_twist,
    "sources": _render_sources,
    "cta": _render_cta,
}

# The order is the argument. A carousel that does not follow it is rejected by
# quality.visual before it can publish.
SLIDE_ORDER = ("cover", "scale", "twist", "sources", "cta")


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def render_carousel(carousel: InstagramCarousel, out_dir: Path,
                    image_loader: ImageLoader | None = None) -> list[Path]:
    """Render every slide to a PNG, returning the file paths in order."""
    loader = image_loader or default_image_loader
    out_dir.mkdir(parents=True, exist_ok=True)
    story = carousel.story

    paths: list[Path] = []
    for i, slide in enumerate(carousel.slides, 1):
        # Tone is per slide, because it encodes the job the slide does. A
        # disputed or sensitive story overrides all five, which is handled
        # inside tone_for rather than here.
        tone = theme.tone_for(story, category=carousel.category, role=slide.role)
        render = _RENDERERS.get(slide.role, _render_twist)
        img = render(slide, carousel, story, tone, loader)
        path = out_dir / f"slide_{i}.png"
        img.convert("RGB").save(path, "PNG")
        slide.image_file = str(path)
        paths.append(path)
        log.info("rendered %s (%s)", path.name, slide.role)
    return paths
