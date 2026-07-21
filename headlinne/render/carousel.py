"""Render Instagram carousel slides to PNG files with Pillow.

The layouts are built from the shared design system in ``render.theme`` so all
three slide kinds read as one template:

  - cover: a full-bleed article photo (or a designed brand fallback) under a
    cinematic scrim, with the brand bar, a dateline eyebrow, a big Anton title,
    a one-line hook, page-progress pips and a SWIPE affordance.
  - story: the article photo with the same brand bar, a large ghosted index
    number, an accent rule, the headline, a short "what happened + why", and a
    SOURCES trust line naming the outlets that corroborated the story.
  - cta: a warm ink slide with the logo, a sign-off, follow / save engagement
    pills and the website.

Backgrounds come from the article image URL when available. If an image cannot
be loaded (or is too small to look sharp) we fall back to a designed,
category-tinted brand background so a slide is never flat or empty.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageDraw, ImageFilter

from ..config import (GEO_USE_FLAG, INSTAGRAM_HANDLE, SLIDE_H, SLIDE_W, WEBSITE)
from ..logging_setup import get_logger
from ..models import InstagramCarousel, Slide
from . import fonts, theme
from .flag_text import render_flag_text

log = get_logger("render.carousel")

ImageLoader = Callable[[Optional[str]], Optional[Image.Image]]

MARGIN = theme.MARGIN
BOTTOM_ANCHOR = 1180            # text blocks sit above this; furniture sits below


# --------------------------------------------------------------------------- #
# Image loading (unchanged behaviour: upgrade thumbnails, cover-fit, sharpen)
# --------------------------------------------------------------------------- #
_MIN_SOURCE_PX = 360
_UPGRADE_WIDTHS = (2048, 1536, 1024)


def _upgrade_candidates(url: str) -> list[str]:
    """Ordered higher-resolution variants of a thumbnail URL, largest first."""
    if not url:
        return []
    candidates: list[str] = []
    stripped = re.sub(r"-\d{2,4}x\d{2,4}(?=\.(?:jpg|jpeg|png|webp)\b)", "", url, flags=re.I)
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

            resp = requests.get(url, timeout=12, headers={"User-Agent": "Headlinne/1.0"})
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


def _cover_fit(img: Image.Image, w: int, h: int) -> Image.Image:
    """Scale and centre-crop to exactly w x h, then sharpen."""
    img = img.convert("RGB")
    src_w, src_h = img.size
    scale = max(w / src_w, h / src_h)
    new = (max(1, int(src_w * scale)), max(1, int(src_h * scale)))
    img = img.resize(new, Image.LANCZOS)
    left = (img.width - w) // 2
    top = (img.height - h) // 2
    img = img.crop((left, top, left + w, top + h))
    if scale > 1.05:
        img = img.filter(ImageFilter.UnsharpMask(radius=2.2, percent=135, threshold=2))
    else:
        img = img.filter(ImageFilter.UnsharpMask(radius=1.1, percent=75, threshold=3))
    return img.convert("RGBA")


def _photo_or_fallback(slide: Slide, category: str, loader: ImageLoader) -> Image.Image:
    """A full-canvas photo background, or the designed brand fallback."""
    img = loader(slide.image_url)
    if img is not None and min(img.size) >= _MIN_SOURCE_PX:
        try:
            return _cover_fit(img, SLIDE_W, SLIDE_H)
        except Exception as exc:  # pragma: no cover
            log.warning("cover-fit failed: %s", exc)
    elif img is not None:
        log.info("background %dx%d too small for a sharp slide, using fallback",
                 img.size[0], img.size[1])
    return theme.brand_fallback(SLIDE_W, SLIDE_H, category,
                                slide.headline or category)


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #
def _draw_block_with_shadow(canvas: Image.Image, lines: list[str], font, *,
                            x: int, y: int, fill, line_spacing: float,
                            shadow_alpha: int = 150) -> int:
    """Draw wrapped lines with a soft drop shadow (keeps type legible on bright
    photos). Returns the y below the block."""
    lh = int(fonts.line_height(font) * line_spacing)
    if shadow_alpha:
        shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(shadow)
        cy = y
        for line in lines:
            sdraw.text((x, cy), line, font=font, fill=(0, 0, 0, shadow_alpha))
            cy += lh
        shadow = shadow.filter(ImageFilter.GaussianBlur(6))
        canvas.alpha_composite(shadow)
    draw = ImageDraw.Draw(canvas)
    cy = y
    for line in lines:
        draw.text((x, cy), line, font=font, fill=fill)
        cy += lh
    return cy


def _dateline(carousel_time: str) -> str:
    """A human dateline like 'MON, 21 JUL' derived from the slot time."""
    try:
        d = datetime.fromisoformat(carousel_time).date()
    except (ValueError, TypeError):
        d = date.today()
    return d.strftime("%a, %d %b").upper()


# --------------------------------------------------------------------------- #
# Cover slide
# --------------------------------------------------------------------------- #
def _render_cover(slide: Slide, category: str, loader: ImageLoader,
                  *, total: int, dateline: str) -> Image.Image:
    canvas = _photo_or_fallback(slide, category, loader)
    canvas.alpha_composite(theme.cinematic_scrim(SLIDE_W, SLIDE_H))
    draw = ImageDraw.Draw(canvas)
    accent = theme.accent_for(category)

    theme.draw_top_bar(canvas, draw, category)

    max_w = SLIDE_W - 2 * MARGIN

    # Title (the model's engaging hook, white for legibility on any photo).
    title_font, title_lines, title_h = fonts.fit_block(
        fonts.title_font, slide.headline,
        max_width=max_w, max_height=int(SLIDE_H * 0.40), start_size=136, min_size=72,
    )

    # Optional one-line hook under the title.
    sub_lines: list[str] = []
    sub_font = fonts.body_font(40, weight=500)
    sub_h = 0
    if slide.subtitle:
        sub_font, sub_lines, sub_h = fonts.fit_block(
            fonts.body_font, slide.subtitle,
            max_width=max_w, max_height=int(SLIDE_H * 0.12), start_size=42,
            min_size=30, weight=500,
        )

    eyebrow_font = fonts.label_font(27, weight=800)
    eyebrow = f"YOUR DAILY BRIEF  ·  {dateline}"
    eyebrow_h = fonts.line_height(eyebrow_font)
    rule_gap = 26
    rule_h = 7
    eb_gap = 30
    sub_gap = 26 if sub_lines else 0

    block_h = eyebrow_h + eb_gap + rule_h + rule_gap + title_h + (sub_gap + sub_h)
    y = BOTTOM_ANCHOR - block_h

    # Eyebrow (dateline), with a soft shadow so the accent colour holds up on
    # bright photos.
    theme.draw_tracked_shadowed(canvas, (MARGIN, y), eyebrow, eyebrow_font,
                                fill=theme.rgba(accent), tracking=2.2, shadow_alpha=150)
    y += eyebrow_h + eb_gap
    # Accent rule.
    theme.draw_accent_rule(draw, MARGIN, y, accent, width=104, thickness=rule_h)
    y += rule_h + rule_gap
    # Title.
    if GEO_USE_FLAG and category == "Geopolitics":
        y = _draw_flag_title(canvas, title_lines, title_font, x=MARGIN, y=y)
    else:
        y = _draw_block_with_shadow(canvas, title_lines, title_font, x=MARGIN, y=y,
                                    fill=theme.rgba(theme.TEXT_PRIMARY),
                                    line_spacing=1.06, shadow_alpha=160)
    # Hook.
    if sub_lines:
        y += sub_gap - int(fonts.line_height(title_font) * 0.0)
        _draw_block_with_shadow(canvas, sub_lines, sub_font, x=MARGIN, y=y,
                                fill=theme.rgba(theme.TEXT_SECONDARY),
                                line_spacing=1.2, shadow_alpha=120)

    theme.draw_progress(canvas, draw, total=total, active=0, accent=accent)
    theme.draw_swipe_hint(draw, accent, y=theme.BOTTOM_BAR_Y - 12)
    return canvas


def _draw_flag_title(canvas: Image.Image, lines: list[str], font, *,
                     x: int, y: int) -> int:
    """Legacy stars-and-stripes 'Geo' treatment (opt-in via GEO_USE_FLAG)."""
    draw = ImageDraw.Draw(canvas)
    lh = int(fonts.line_height(font) * 1.06)
    white = theme.rgba(theme.TEXT_PRIMARY)
    for line in lines:
        if "Geo" in line:
            draw.text((x, y), line, font=font, fill=white)
            idx = line.find("Geo")
            prefix = line[:idx]
            x_geo = x + fonts.text_width(font, prefix) if prefix else x
            geo_bbox = font.getbbox("Geo")
            flag_img = render_flag_text("Geo", font, pad=6)
            canvas.alpha_composite(flag_img, (max(0, int(x_geo + geo_bbox[0] - 6)),
                                              max(0, int(y + geo_bbox[1] - 6))))
        else:
            draw.text((x, y), line, font=font, fill=white)
        y += lh
    return y


# --------------------------------------------------------------------------- #
# Story slide
# --------------------------------------------------------------------------- #
def _render_story(slide: Slide, category: str, loader: ImageLoader,
                  *, position: int, total: int) -> Image.Image:
    canvas = _photo_or_fallback(slide, category, loader)
    canvas.alpha_composite(theme.cinematic_scrim(SLIDE_W, SLIDE_H))
    draw = ImageDraw.Draw(canvas)
    accent = theme.accent_for(category)

    theme.draw_top_bar(canvas, draw, category)
    _draw_ghost_index(canvas, slide.index, accent)

    max_w = SLIDE_W - 2 * MARGIN

    head_font, head_lines, head_h = fonts.fit_block(
        fonts.title_font, slide.headline,
        max_width=max_w, max_height=int(SLIDE_H * 0.30), start_size=104, min_size=58,
    )
    exp_font, exp_lines, exp_h = fonts.fit_block(
        fonts.body_font, slide.explanation or "",
        max_width=max_w, max_height=int(SLIDE_H * 0.22),
        start_size=44, min_size=30, weight=400,
    )
    has_exp = bool(exp_lines and exp_lines != [""])

    rule_h = 7
    rule_gap = 30
    head_gap = 28
    src_gap = 34
    src_h = fonts.line_height(fonts.label_font(24, weight=600)) if slide.sources else 0

    block_h = (rule_h + rule_gap + head_h
               + (head_gap + exp_h if has_exp else 0)
               + (src_gap + src_h if slide.sources else 0))
    y = BOTTOM_ANCHOR - block_h

    theme.draw_accent_rule(draw, MARGIN, y, accent, width=92, thickness=rule_h)
    y += rule_h + rule_gap
    y = _draw_block_with_shadow(canvas, head_lines, head_font, x=MARGIN, y=y,
                                fill=theme.rgba(theme.TEXT_PRIMARY),
                                line_spacing=1.05, shadow_alpha=160)
    if has_exp:
        y += head_gap
        y = _draw_block_with_shadow(canvas, exp_lines, exp_font, x=MARGIN, y=y,
                                    fill=theme.rgba(theme.TEXT_SECONDARY),
                                    line_spacing=1.2, shadow_alpha=120)
    if slide.sources:
        y += src_gap
        theme.draw_source_line(draw, slide.sources, accent, x=MARGIN + 6, y=y)

    theme.draw_progress(canvas, draw, total=total, active=position, accent=accent)
    theme.draw_handle(draw, WEBSITE)
    return canvas


def _draw_ghost_index(canvas: Image.Image, index: int, accent) -> None:
    """A large, low-opacity index number ('01') in the upper-right, as an
    editorial anchor that also signals 'story N of the set'."""
    if not index:
        return
    label = f"{index:02d}"
    font = fonts.title_font(300)
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ldraw = ImageDraw.Draw(layer)
    bbox = font.getbbox(label)
    tw = bbox[2] - bbox[0]
    x = SLIDE_W - MARGIN - tw
    y = int(SLIDE_H * 0.19)
    ldraw.text((x - bbox[0], y - bbox[1]), label, font=font, fill=theme.rgba(accent, 46))
    canvas.alpha_composite(layer)


# --------------------------------------------------------------------------- #
# CTA slide
# --------------------------------------------------------------------------- #
def _render_cta(slide: Slide, category: str, *, total: int) -> Image.Image:
    canvas = theme.panel_gradient(SLIDE_W, SLIDE_H, theme.INK)
    # Soft terracotta glow behind the logo.
    glow = Image.new("RGBA", (SLIDE_W, SLIDE_H), (0, 0, 0, 0))
    gmask = Image.new("L", (SLIDE_W, SLIDE_H), 0)
    gdraw = ImageDraw.Draw(gmask)
    cx, cy = SLIDE_W // 2, int(SLIDE_H * 0.34)
    r = int(SLIDE_W * 0.5)
    gdraw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=120)
    gmask = gmask.filter(ImageFilter.GaussianBlur(150))
    glow_col = theme.mix(theme.hex_to_rgb(theme.INK), theme.hex_to_rgb(theme.BRAND_TERRACOTTA), 0.6)
    glow = Image.new("RGBA", (SLIDE_W, SLIDE_H), theme.rgba(glow_col))
    glow.putalpha(gmask)
    canvas = Image.alpha_composite(canvas, glow)
    draw = ImageDraw.Draw(canvas)

    # Logo mark, centred upper third.
    mark = theme.logo_mark(224)
    logo_bottom = int(SLIDE_H * 0.20)
    if mark is not None:
        lx = (SLIDE_W - 224) // 2
        ly = int(SLIDE_H * 0.17)
        canvas.alpha_composite(mark, (lx, ly))
        logo_bottom = ly + 224

    max_w = SLIDE_W - 2 * MARGIN

    # Sign-off headline.
    head = slide.headline or "That's your brief for today."
    head_font, head_lines, head_h = fonts.fit_block(
        fonts.title_font, head,
        max_width=max_w, max_height=int(SLIDE_H * 0.20), start_size=92, min_size=52,
    )
    y = logo_bottom + 82
    lh = int(fonts.line_height(head_font) * 1.06)
    for line in head_lines:
        w = fonts.text_width(head_font, line)
        draw.text((MARGIN + (max_w - w) // 2, y), line, font=head_font,
                  fill=theme.rgba(theme.TEXT_PRIMARY))
        y += lh

    # Sub-line.
    sub = slide.subtitle or "Personalised news, minus the noise."
    sub_font = fonts.body_font(40, weight=500)
    sub_lines = fonts.wrap_text(sub_font, sub, max_w)
    y += 18
    slh = int(fonts.line_height(sub_font) * 1.2)
    for line in sub_lines:
        w = fonts.text_width(sub_font, line)
        draw.text((MARGIN + (max_w - w) // 2, y), line, font=sub_font,
                  fill=theme.rgba(theme.TEXT_SECONDARY))
        y += slh

    # Engagement pills: FOLLOW (solid) + SAVE (outline), centred as a pair.
    y += 60
    _draw_cta_pills(draw, y)

    # Website, terracotta, near the bottom.
    web_font = fonts.title_font(72)
    ww = fonts.text_width(web_font, WEBSITE)
    draw.text((MARGIN + (max_w - ww) // 2, int(SLIDE_H * 0.82)), WEBSITE,
              font=web_font, fill=theme.rgba(theme.BRAND_TERRACOTTA))
    return canvas


def _draw_cta_pills(draw: ImageDraw.ImageDraw, y: int) -> None:
    terra = theme.hex_to_rgb(theme.BRAND_TERRACOTTA)
    follow_label = f"FOLLOW {INSTAGRAM_HANDLE}"
    save_label = "SAVE THIS"
    font = fonts.label_font(26, weight=800)
    tr = 1.4
    pad_x, pad_y = 34, 20
    fh = fonts.line_height(font)

    fw = fonts.tracked_width(font, follow_label, tr) + pad_x * 2
    sw = fonts.tracked_width(font, save_label, tr) + pad_x * 2
    h = fh + pad_y * 2
    gap = 24
    total_w = fw + gap + sw
    x0 = (SLIDE_W - total_w) // 2

    # Follow (solid terracotta, dark text).
    draw.rounded_rectangle([x0, y, x0 + fw, y + h], radius=h // 2, fill=theme.rgba(terra))
    ty = y + pad_y - font.getbbox(follow_label)[1]
    fonts.draw_tracked(draw, (x0 + pad_x, ty), follow_label, font,
                       fill=theme.rgba(theme.INK), tracking=tr)
    # Save (outline).
    sx = x0 + fw + gap
    draw.rounded_rectangle([sx, y, sx + sw, y + h], radius=h // 2,
                           outline=theme.rgba(theme.TEXT_SECONDARY), width=3)
    fonts.draw_tracked(draw, (sx + pad_x, ty), save_label, font,
                       fill=theme.rgba(theme.TEXT_SECONDARY), tracking=tr)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def render_carousel(carousel: InstagramCarousel, out_dir: Path,
                    image_loader: ImageLoader | None = None) -> list[Path]:
    """Render every slide to a PNG, returning the file paths in order."""
    loader = image_loader or default_image_loader
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    category = carousel.category
    total = len(carousel.slides)
    dateline = _dateline(carousel.scheduled_time)

    for i, slide in enumerate(carousel.slides, 1):
        position = i - 1
        if slide.role == "cover":
            img = _render_cover(slide, category, loader, total=total, dateline=dateline)
        elif slide.role == "cta":
            img = _render_cta(slide, category, total=total)
        else:
            img = _render_story(slide, category, loader, position=position, total=total)

        path = out_dir / f"slide_{i}.png"
        img.convert("RGB").save(path, "PNG")
        slide.image_file = str(path)
        paths.append(path)
        log.info("rendered %s", path.name)

    return paths
