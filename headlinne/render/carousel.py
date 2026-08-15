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

from ..config import (CATEGORY_LABELS, GEO_USE_FLAG, INSTAGRAM_HANDLE,
                      SLIDE_H, SLIDE_W, WEBSITE)
from ..logging_setup import get_logger
from ..models import InstagramCarousel, Slide
from . import fonts, slides, theme
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


# Cover-fitting now lives in the shared design system so the carousel, the reel
# plates and the story card all treat photography identically.
_cover_fit = theme.cover_fit


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
    """A human dateline like 'MON 21 JUL' derived from the slot time."""
    try:
        d = datetime.fromisoformat(carousel_time).date()
    except (ValueError, TypeError):
        d = date.today()
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}".upper()


# --------------------------------------------------------------------------- #
# Cover slide
# --------------------------------------------------------------------------- #
def _render_cover(slide: Slide, category: str, loader: ImageLoader,
                  *, total: int, dateline: str) -> Image.Image:
    canvas = _photo_or_fallback(slide, category, loader)
    canvas.alpha_composite(theme.cinematic_scrim(SLIDE_W, SLIDE_H))
    draw = ImageDraw.Draw(canvas)
    accent = theme.accent_for(category)

    theme.draw_masthead(canvas, draw, category)

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
    # removed: Instagram draws its own swipe affordance
    # theme.draw_swipe_hint(draw, accent, y=theme.BOTTOM_BAR_Y - 12)
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

    theme.draw_masthead(canvas, draw, category)
    # The ghosted "01" is gone. It sat at an opacity that read as a compression
    # fault rather than as design, and it numbered a sequence Instagram already
    # numbers with its own dots. Pip carries the slide instead.
    pose = theme.pose_for("cover" if slide.role == "cover" else "explainer")
    if pose:
        theme.draw_pip(canvas, pose, scale=8,
                       x=SLIDE_W - theme.MARGIN - 26 * 8, y=190)

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
    """The last slide. Pip asks for the click; the domain is the loudest thing.

    Previously a dark panel with a terracotta glow behind the logo mark, which
    was the only slide in the set that did not sit on paper.
    """
    canvas = theme.paper(SLIDE_W, SLIDE_H)
    draw = ImageDraw.Draw(canvas)
    accent = theme.accent_for(category)
    theme.draw_masthead(canvas, draw, category)

    pose = theme.pose_for("cta")
    if pose:
        theme.draw_pip(canvas, pose, scale=15,
                       x=MARGIN - 30, y=int(SLIDE_H * 0.20))

    y = int(SLIDE_H * 0.54)
    draw.text((MARGIN, y), "READ THE FULL STORY",
              font=fonts.label_font(30, 700), fill=theme.rgba(accent))
    y += 54
    head_font = fonts.title_font(104, 800)
    draw.text((MARGIN, y), WEBSITE, font=head_font,
              fill=theme.rgba(theme.TEXT_PRIMARY))
    y += 132
    sub_font = fonts.body_font(38, weight=500)
    subtitle = slide.subtitle or "Every source on this story, side by side."
    for line in fonts.wrap_text(sub_font, subtitle, SLIDE_W - MARGIN * 2):
        draw.text((MARGIN, y), line, font=sub_font,
                  fill=theme.rgba(theme.TEXT_SECONDARY))
        y += int(fonts.line_height(sub_font) * 1.25)

    _draw_footer_rule(canvas, draw) if "_draw_footer_rule" in globals() else None
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
def _lead_number(text: str) -> tuple[str, str] | None:
    """A quantity the scale slide can build itself around, if the copy opens with one.

    The scale slide exists to make one number mean something, so it is only the
    right slide when there is a number to enlarge, and only when the number is
    what the line leads with. Anything else falls through to the twist.
    """
    m = re.match(r"\s*([0-9][0-9,.]*)\s+([A-Za-z][A-Za-z/]{1,14})\b", text or "")
    if not m:
        return None
    return m.group(1), m.group(2)


# Each slide carries its own temperature, as the design has it: the cover runs
# hot, the scale slide sits on the brand terracotta, the twist is the marigold
# that means "look again", and the close is the green of a checked source.
_SLIDE_TONE = {
    "cover": (206, 62, 34),
    "scale": "Technology",
    "twist": "Geopolitics",
    "close": "Finance",
    "cta": "Technology",
}


def _tone(kind: str):
    value = _SLIDE_TONE.get(kind, "Technology")
    return value if isinstance(value, tuple) else theme.accent_for(value)


def render_carousel(carousel: InstagramCarousel, out_dir: Path,
                    image_loader: ImageLoader | None = None) -> list[Path]:
    """Render every slide to a PNG, returning the file paths in order.

    The five slides of the design do five different jobs, so the role on the
    slide picks the layout rather than the layout being one template with the
    copy swapped. Story slides become the twist by default, the last of them
    closes on the sourcing, and one that opens on a quantity becomes the scale
    slide instead.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    dateline = _dateline(carousel.scheduled_time)
    kicker = CATEGORY_LABELS.get(carousel.category, carousel.category)

    story_positions = [i for i, sl in enumerate(carousel.slides)
                       if sl.role not in ("cover", "cta")]
    last_story = story_positions[-1] if story_positions else -1

    for i, slide in enumerate(carousel.slides):
        raw_total, raw_agree = slides.source_counts(
            slide.sources, getattr(slide, "outlets", ()),
            getattr(slide, "agree", 0))
        agree, total = slides.display_ratio(raw_agree, raw_total)
        if slide.role == "cover":
            img = slides.slide_cover(
                kicker=kicker, headline=slide.headline or carousel.title,
                standfirst=slide.subtitle, dateline=dateline,
                say=slide.subtitle or None, sources=total, agree=agree,
                tone=_tone("cover"))
        elif slide.role == "cta":
            img = slides.slide_cta(
                body=slide.explanation or slide.subtitle, dateline=dateline,
                say=slides.pip_line("cta"), sources=total, agree=agree,
                tone=_tone("cta"))
        elif carousel.kind == "brief":
            img = slides.slide_brief(
                kicker=CATEGORY_LABELS.get(slide.subtitle, slide.subtitle) or kicker,
                headline=slide.headline, standfirst=slide.explanation,
                dateline=dateline, index=story_positions.index(i) + 1,
                of=len(story_positions), sources=total, agree=agree,
                pose=slides.BRIEF_POSES[story_positions.index(i)
                                        % len(slides.BRIEF_POSES)],
                tone=_tone("scale"))
        elif i == last_story and total:
            img = slides.slide_close(
                outlets=slide.sources, body=slide.explanation,
                dateline=dateline, sources=total, agree=agree,
                say=slides.pip_line("close", agree=agree, total=total),
                tone=_tone("close"))
        else:
            number = _lead_number(slide.headline)
            if number:
                img = slides.slide_scale(
                    kicker=slide.subtitle or kicker,
                    number=number[0], unit=number[1],
                    body=slide.explanation, dateline=dateline,
                    say=slides.pip_line("scale"), tone=_tone("scale"))
            else:
                img = slides.slide_twist(
                    kicker=slide.subtitle or kicker, headline=slide.headline,
                    body=slide.explanation, dateline=dateline,
                    say=slides.pip_line("scale"), tone=_tone("scale"))

        path = out_dir / f"slide_{i + 1}.png"
        img.convert("RGB").save(path, "PNG")
        slide.image_file = str(path)
        paths.append(path)
        log.info("rendered %s (%s)", path.name, slide.role)

    return paths
