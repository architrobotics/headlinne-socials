"""The daily story card: one article, start to finish, on one image.

A carousel asks a reader to swipe, which means every slide is another chance for
them to leave. This format asks for something different. Everything is on one
frame, so the natural response is not to page through it but to keep it, and a
save is worth far more to a post's reach than a swipe is.

The layout is a numbered rail: the story enters at the top as a headline and
descends through four fixed stops, so a reader always knows where they are and
what kind of information comes next. The stops are owned by the code rather than
the model, because the value of the format is that it is the *same* shape every
day. That is what makes it recognisable in a feed.

Everything is fitted rather than positioned. The headline takes what it needs,
the standfirst takes what it needs, and the rail is given whatever is left and
divides it between the steps, shrinking their type until it fits. So a long
story and a short one both produce a card with no overflow and no dead space.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageDraw

from ..config import SLIDE_H, SLIDE_W, WEBSITE
from ..logging_setup import get_logger
from ..models import StoryCard
from . import fonts, theme
from .carousel import default_image_loader

log = get_logger("render.story_card")

ImageLoader = Callable[[Optional[str]], Optional[Image.Image]]

MARGIN = theme.MARGIN
CONTENT_W = SLIDE_W - 2 * MARGIN

HEAD_TOP = 166                  # below the brand bar
RAIL_BOTTOM = 1178              # above the footer
FOOTER_Y = 1218
HEAD_TO_RAIL = 44               # breathing room between the two blocks

# The rail's geometry.
DOT = 46                        # numbered marker diameter
RAIL_X = MARGIN + DOT // 2      # centre line of the rail
STEP_TEXT_X = MARGIN + DOT + 30
STEP_TEXT_W = SLIDE_W - MARGIN - STEP_TEXT_X

STEP_GAP = 22                   # between one step and the next
STEP_MAX_LINES = 3
LABEL_SIZE = 23
BODY_LINE_SPACING = 1.24

# The header needs at least this much to hold an eyebrow, a rule, a two-line
# headline and a two-line standfirst without any of them becoming unreadable.
# The rail may never eat into it: it shrinks its own type instead. Both blocks
# have a floor, and between them they are what makes the character limits in
# generate/story_card.py the numbers they are.
HEADER_MIN = 372


def _dateline(scheduled_time: str) -> str:
    try:
        day = datetime.fromisoformat(scheduled_time).date()
    except (TypeError, ValueError):
        day = date.today()
    return day.strftime("%a, %d %b").upper()


def _background(card: StoryCard, loader: ImageLoader) -> Image.Image:
    """The article photo as a dimmed texture, or the designed brand panel.

    The photo is pushed almost all the way down rather than shown properly. This
    card is dense with text, and a legible photo behind twelve lines of copy
    fights every one of them. Kept at this level it still gives the card a
    subject and a colour temperature, which a flat panel cannot.
    """
    image = loader(card.image_url) if card.image_url else None
    if image is not None and min(image.size) >= 320:
        try:
            plate = theme.cover_fit(image, SLIDE_W, SLIDE_H)
            ink = theme.hex_to_rgb(theme.INK)
            veil = Image.new("RGBA", (SLIDE_W, SLIDE_H), theme.rgba(ink, 226))
            plate = Image.alpha_composite(plate, veil)
            # A little extra weight at the very bottom so the footer sits on a
            # firm base regardless of what the photo does down there.
            ramp = theme.alpha_ramp(SLIDE_H, [(0.0, 0), (0.7, 0), (1.0, 90)])
            layer = Image.new("RGBA", (SLIDE_W, SLIDE_H), theme.rgba(ink, 255))
            layer.putalpha(ramp.resize((SLIDE_W, SLIDE_H)))
            return Image.alpha_composite(plate, layer)
        except Exception as exc:  # pragma: no cover - a bad image must not fail
            log.warning("story card background failed: %s", exc)
    # No ghost mark: this card is mostly body copy, and the oversized logo
    # reads as a smudge behind it rather than as texture.
    return theme.paper(SLIDE_W, SLIDE_H)


def _unused_background(card, loader):
    return theme.brand_fallback(SLIDE_W, SLIDE_H, card.category,
                                card.headline or card.category, ghost_mark=False)


def _layout_steps(card: StoryCard, available: int):
    """Wrap every step, shrinking the whole rail until it fits `available`.

    Laid out before the header, and this is the important part: the header then
    gets whatever is left over. Doing it the other way round is what produces a
    card whose last line of every step is quietly cut off, which is the one
    failure this format cannot survive, because the truncated line is usually
    the one carrying the point.
    """
    steps = card.steps[:5]
    label_font = fonts.label_font(LABEL_SIZE, weight=800)
    label_h = fonts.line_height(label_font)

    blocks: list = []
    for size in range(33, 22, -1):
        font = fonts.body_font(size, weight=400)
        line_h = int(fonts.line_height(font) * BODY_LINE_SPACING)
        blocks = []
        total = 0
        for step in steps:
            lines = fonts.wrap_text(font, step.text, STEP_TEXT_W)[:STEP_MAX_LINES] \
                if step.text.strip() else []
            height = max(DOT, label_h + 10 + len(lines) * line_h)
            blocks.append((step, font, lines, line_h, height))
            total += height
        total += STEP_GAP * max(0, len(steps) - 1)
        if total <= available:
            return blocks, total
    # Nothing fit even at the smallest size. Return the smallest anyway: the
    # caller has already reserved the header's minimum, so this overruns by a
    # few pixels at worst rather than colliding with the footer.
    return blocks, total


def _draw_header(canvas: Image.Image, draw: ImageDraw.ImageDraw,
                 card: StoryCard, accent, *, budget: int) -> int:
    """Eyebrow, rule, headline and standfirst, fitted into `budget` pixels.

    Returns the y the copy actually ended at, which is usually well short of the
    budget. Anything placed after the header must measure from this rather than
    from the budget, or it lands on top of the standfirst.
    """
    theme.draw_masthead(canvas, draw, card.category,
                        date_text=getattr(card, "date_label", ""))


    y = HEAD_TOP
    eyebrow = f"THE FULL STORY  ·  {_dateline(card.scheduled_time)}"
    eyebrow_font = fonts.label_font(26, weight=800)
    theme.draw_tracked_shadowed(canvas, (MARGIN, y), eyebrow, eyebrow_font,
                                fill=theme.rgba(accent), tracking=2.2,
                                shadow_alpha=120)
    y += fonts.line_height(eyebrow_font) + 22

    theme.draw_accent_rule(draw, MARGIN, y, accent, width=104, thickness=7)
    y += 7 + 26

    used = y - HEAD_TOP
    # The standfirst gets a fixed share of what is left and the headline takes
    # the rest, so a long headline shrinks rather than pushing the standfirst
    # off the card.
    stand_room = 96 if card.standfirst else 0
    head_room = max(120, budget - used - stand_room - 18)

    head_font, head_lines, _ = fonts.fit_block(
        fonts.title_font, card.headline, max_width=CONTENT_W,
        max_height=head_room, start_size=96, min_size=46, line_spacing=1.05)
    lh = int(fonts.line_height(head_font) * 1.05)
    for line in head_lines:
        draw.text((MARGIN, y), line, font=head_font,
                  fill=theme.rgba(theme.TEXT_PRIMARY))
        y += lh

    if card.standfirst:
        y += 16
        sub_font, sub_lines, _ = fonts.fit_block(
            fonts.body_font, card.standfirst, max_width=CONTENT_W,
            max_height=stand_room, start_size=34, min_size=25, weight=500,
            line_spacing=1.2)
        slh = int(fonts.line_height(sub_font) * 1.2)
        for line in sub_lines:
            draw.text((MARGIN, y), line, font=sub_font,
                      fill=theme.rgba(theme.TEXT_SECONDARY))
            y += slh
    return y


def _draw_rail(canvas: Image.Image, draw: ImageDraw.ImageDraw, blocks,
               accent, *, top: int) -> None:
    """Draw the numbered steps from a pre-measured layout."""
    if not blocks:
        return

    label_font = fonts.label_font(LABEL_SIZE, weight=800)
    label_h = fonts.line_height(label_font)
    number_font = fonts.label_font(26, weight=800)

    # The connecting line runs from the first marker to the last, drawn first so
    # the markers sit on top of it.
    tops = []
    y = top
    for _step, _font, _lines, _line_h, height in blocks:
        tops.append(y)
        y += height + STEP_GAP
    if len(tops) > 1:
        draw.rounded_rectangle([RAIL_X - 2, tops[0] + DOT // 2,
                                RAIL_X + 2, tops[-1] + DOT // 2],
                               radius=2, fill=theme.rgba(theme.TEXT_MUTED, 110))

    for i, (step, font, lines, line_h, _height) in enumerate(blocks):
        y = tops[i]
        cy = y + DOT // 2
        draw.ellipse([RAIL_X - DOT // 2, cy - DOT // 2,
                      RAIL_X + DOT // 2, cy + DOT // 2], fill=theme.rgba(accent))
        number = str(i + 1)
        nb = number_font.getbbox(number)
        draw.text((RAIL_X - (nb[2] - nb[0]) // 2 - nb[0],
                   cy - (nb[3] - nb[1]) // 2 - nb[1]), number, font=number_font,
                  fill=theme.rgba(theme.INK))

        ty = y + 2
        fonts.draw_tracked(draw, (STEP_TEXT_X, ty), step.label.upper(),
                           label_font, fill=theme.rgba(accent), tracking=1.9)
        ty += label_h + 10
        for line in lines:
            draw.text((STEP_TEXT_X, ty), line, font=font,
                      fill=theme.rgba(theme.TEXT_SECONDARY))
            ty += line_h


def _draw_footer(canvas: Image.Image, draw: ImageDraw.ImageDraw,
                 card: StoryCard, accent) -> None:
    """Sources on the left, the save prompt on the right."""
    y = FOOTER_Y
    draw.rounded_rectangle([MARGIN, y - 22, SLIDE_W - MARGIN, y - 20],
                           radius=1, fill=theme.rgba(theme.TEXT_MUTED, 80))

    if card.sources:
        theme.draw_source_line(draw, card.sources, accent, x=MARGIN + 8, y=y)
    else:
        web_font = fonts.label_font(27, weight=800)
        fonts.draw_tracked(draw, (MARGIN, y), WEBSITE, web_font,
                           fill=theme.rgba(theme.BRAND_TERRACOTTA), tracking=1.4)

    label = "SAVE THIS"
    font = fonts.label_font(24, weight=800)
    tracking = 1.6
    text_w = fonts.tracked_width(font, label, tracking)
    pad_x, pad_y = 24, 13
    w = text_w + pad_x * 2
    h = fonts.line_height(font) + pad_y * 2
    x0 = SLIDE_W - MARGIN - w
    y0 = y - 8
    draw.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=h // 2,
                           outline=theme.rgba(accent), width=3)
    fonts.draw_tracked(draw, (x0 + pad_x, y0 + pad_y - font.getbbox(label)[1]),
                       label, font, fill=theme.rgba(accent), tracking=tracking)

    if card.sources:
        # The website only moves to the bottom line when sources took the left
        # slot, so the card always carries the address exactly once.
        web_font = fonts.label_font(26, weight=800)
        fonts.draw_tracked(draw, (MARGIN, y + 52), WEBSITE, web_font,
                           fill=theme.rgba(theme.BRAND_TERRACOTTA), tracking=1.4)


def render_story_card(card: StoryCard, out_path: Path,
                      image_loader: ImageLoader | None = None) -> Path:
    """Render the day's story card to a PNG and stamp the path onto the card."""
    loader = image_loader or default_image_loader
    out_path.parent.mkdir(parents=True, exist_ok=True)

    accent = theme.accent_for(card.category)
    canvas = _background(card, loader)
    draw = ImageDraw.Draw(canvas)

    # Measure the rail first, then hand the header whatever is left.
    rail_room = RAIL_BOTTOM - (HEAD_TOP + HEADER_MIN + HEAD_TO_RAIL)
    blocks, rail_h = _layout_steps(card, rail_room)
    header_budget = RAIL_BOTTOM - rail_h - HEAD_TO_RAIL - HEAD_TOP

    header_bottom = _draw_header(canvas, draw, card, accent,
                                 budget=header_budget)
    rail_top = HEAD_TOP + header_budget + HEAD_TO_RAIL

    # Pip sits in the clear band between the header and the rail, sized to fit
    # it rather than placed at a guessed y - the header grows and shrinks with
    # the headline, so any fixed position eventually lands on top of the text.
    # Sensitive stories carry no mascot at all.
    pose = theme.pose_for("explainer",
                          sensitive=bool(getattr(card, "sensitive", False)))
    band_top = header_bottom + 24
    band_h = rail_top - band_top
    if pose and band_h >= 130:
        scale = max(5, min(9, (band_h - 40) // 24))
        sprite_h = 24 * scale
        theme.draw_pip(canvas, pose, scale=scale,
                       x=SLIDE_W - MARGIN - 26 * scale,
                       y=band_top + (band_h - sprite_h) // 2)

    _draw_rail(canvas, draw, blocks, accent, top=rail_top)
    _draw_footer(canvas, draw, card, accent)

    canvas.convert("RGB").save(out_path, "PNG")
    card.image_file = str(out_path)
    log.info("rendered story card (%d steps) -> %s", len(card.steps), out_path.name)
    return out_path
