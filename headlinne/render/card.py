"""Render a branded square image card for an X (Twitter) post.

X posts are text-first, but attaching a clean, on-brand graphic lifts reach and
makes a roundup scannable in the timeline. The card reuses the same design
system as the Instagram carousel (``render.theme``) so the two channels look
like one brand.

Two kinds:
  - news: an "In {category} today" header, the lead line as a headline, and up
    to three numbered story lines.
  - promo: a brand-forward statement card for the Headlinne feature of the day.

The card is 1080x1080 (square posts display without cropping across clients) and
uses the designed brand background, so it never depends on a photo or the
network at render time.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from ..config import BRAND, CATEGORY_COLORS, INSTAGRAM_HANDLE, WEBSITE
from ..logging_setup import get_logger
from ..models import TwitterPost
from . import fonts, theme

log = get_logger("render.card")

CARD = 1080                     # square
MARGIN = theme.MARGIN
_BOTTOM = CARD - 66             # baseline for the bottom furniture

# Map the short X category labels back to display + accent.
_LABEL_TO_CATEGORY = {"Tech": "Technology", "Finance": "Finance",
                      "Geopolitics": "Geopolitics"}


def _category_of(post: TwitterPost) -> str:
    return _LABEL_TO_CATEGORY.get(post.category, "Technology")


def _eyebrow(post: TwitterPost) -> str:
    if post.kind == "promo":
        return "FROM HEADLINNE"
    label = post.category.upper()
    return f"IN {label} TODAY"


def _bottom_bar(canvas: Image.Image, draw: ImageDraw.ImageDraw, accent) -> None:
    """Website (brand) on the left, handle (muted) on the right."""
    web_font = fonts.label_font(30, weight=800)
    fonts.draw_tracked(draw, (MARGIN, _BOTTOM), WEBSITE, web_font,
                       fill=theme.rgba(theme.BRAND_TERRACOTTA), tracking=1.4)
    handle_font = fonts.label_font(28, weight=700)
    tw = fonts.tracked_width(handle_font, INSTAGRAM_HANDLE, 1.0)
    fonts.draw_tracked(draw, (CARD - MARGIN - tw, _BOTTOM + 1), INSTAGRAM_HANDLE,
                       handle_font, fill=theme.rgba(theme.TEXT_MUTED), tracking=1.0)


def _render_news(post: TwitterPost) -> Image.Image:
    category = _category_of(post)
    accent = theme.accent_for(category)
    canvas = theme.brand_fallback(CARD, CARD, category, post.lead or post.category)
    draw = ImageDraw.Draw(canvas)
    theme.draw_top_bar(canvas, draw, category)

    max_w = CARD - 2 * MARGIN
    y = 196

    # Eyebrow.
    eb_font = fonts.label_font(30, weight=800)
    theme.draw_tracked_shadowed(canvas, (MARGIN, y), _eyebrow(post), eb_font,
                                fill=theme.rgba(accent), tracking=2.4, shadow_alpha=120)
    y += fonts.line_height(eb_font) + 26
    theme.draw_accent_rule(draw, MARGIN, y, accent, width=104, thickness=7)
    y += 7 + 34

    # Lead headline.
    lead = post.lead or "Today's biggest stories"
    head_font, head_lines, head_h = fonts.fit_block(
        fonts.title_font, lead, max_width=max_w, max_height=int(CARD * 0.28),
        start_size=96, min_size=54)
    for line in head_lines:
        draw.text((MARGIN, y), line, font=head_font, fill=theme.rgba(theme.TEXT_PRIMARY))
        y += int(fonts.line_height(head_font) * 1.05)

    # Story lines as a numbered list.
    items = [it for it in (post.items or []) if it.strip()][:3]
    if items:
        y += 26
        num_font = fonts.label_font(30, weight=800)
        item_font = fonts.body_font(38, weight=500)
        chip = 52
        for i, text in enumerate(items, 1):
            # Accent number chip.
            draw.rounded_rectangle([MARGIN, y, MARGIN + chip, y + chip], radius=14,
                                   fill=theme.rgba(accent))
            n = str(i)
            nb = num_font.getbbox(n)
            nx = MARGIN + (chip - (nb[2] - nb[0])) // 2 - nb[0]
            ny = y + (chip - (nb[3] - nb[1])) // 2 - nb[1]
            draw.text((nx, ny), n, font=num_font, fill=theme.rgba(theme.INK))
            # Wrapped text beside it.
            tx = MARGIN + chip + 26
            lines = fonts.wrap_text(item_font, text, max_w - chip - 26)[:2]
            ty = y + (chip - len(lines) * int(fonts.line_height(item_font) * 1.08)) // 2
            ty = max(ty, y - 4)
            for ln in lines:
                draw.text((tx, ty), ln, font=item_font, fill=theme.rgba(theme.TEXT_SECONDARY))
                ty += int(fonts.line_height(item_font) * 1.08)
            y += max(chip, len(lines) * int(fonts.line_height(item_font) * 1.08)) + 22

    _bottom_bar(canvas, draw, accent)
    return canvas


def _render_promo(post: TwitterPost) -> Image.Image:
    terra = theme.hex_to_rgb(theme.BRAND_TERRACOTTA)
    canvas = theme.brand_fallback(CARD, CARD, "Promo", post.lead or "headlinne")
    draw = ImageDraw.Draw(canvas)
    theme.draw_top_bar(canvas, draw, "Promo", pill_text="HEADLINNE", pill_accent=terra)

    max_w = CARD - 2 * MARGIN
    y = 244
    eb_font = fonts.label_font(30, weight=800)
    theme.draw_tracked_shadowed(canvas, (MARGIN, y), "FROM HEADLINNE", eb_font,
                                fill=theme.rgba(terra), tracking=2.4, shadow_alpha=120)
    y += fonts.line_height(eb_font) + 26
    theme.draw_accent_rule(draw, MARGIN, y, terra, width=104, thickness=7)
    y += 7 + 40

    statement = post.lead or "News, made personal."
    head_font, head_lines, _ = fonts.fit_block(
        fonts.title_font, statement, max_width=max_w, max_height=int(CARD * 0.42),
        start_size=104, min_size=56)
    for line in head_lines:
        draw.text((MARGIN, y), line, font=head_font, fill=theme.rgba(theme.TEXT_PRIMARY))
        y += int(fonts.line_height(head_font) * 1.06)

    sub = f"{BRAND} is your personalised, AI-powered news brief."
    sub_font = fonts.body_font(38, weight=500)
    y += 22
    for line in fonts.wrap_text(sub_font, sub, max_w):
        draw.text((MARGIN, y), line, font=sub_font, fill=theme.rgba(theme.TEXT_SECONDARY))
        y += int(fonts.line_height(sub_font) * 1.2)

    _bottom_bar(canvas, draw, terra)
    return canvas


def render_twitter_card(post: TwitterPost, out_path: Path) -> Path:
    """Render a post's card to `out_path` (PNG) and return the path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img = _render_promo(post) if post.kind == "promo" else _render_news(post)
    img.convert("RGB").save(out_path, "PNG")
    post.image_file = str(out_path)
    log.info("rendered X %s card -> %s", post.kind, out_path.name)
    return out_path
