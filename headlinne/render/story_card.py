"""The daily story card: one article, walked through on a single image.

The counterweight to the carousel. A carousel asks for a swipe, and every swipe
is another chance to leave; this asks for a save, which is worth far more to a
post's reach. Everything a reader needs is on one frame, so the natural response
is to keep it.

The rail is always the same four stops, fixed in code and not up to the model:
what happened, how we got here, why it matters, what to watch. A reader who has
seen one of these knows where the "does this affect me" line will be before they
have finished the headline. That predictability is the format.

The layout measures the steps first and hands the headline whatever is left, so
a long story shrinks its type rather than silently truncating the line that
carries the point.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from PIL import Image, ImageDraw

from ..config import SLIDE_H, SLIDE_W
from ..logging_setup import get_logger
from ..models import StoryCard
from . import fonts, theme

log = get_logger("render.story_card")

MARGIN = theme.MARGIN
CONTENT_W = SLIDE_W - 2 * MARGIN

HEAD_TOP = 176                  # below the masthead rule
# The rail must clear the receipt, and the receipt must clear the footer rule.
# Working up from the bottom: the footer rule is 132 from the bottom, the
# receipt block runs about 170px from its own top, and each boundary gets 30px
# so the card never reads as crowded even when every step wraps to three lines.
RECEIPT_FROM_BOTTOM = 300       # receipt top, i.e. y = 1050 on a 1350 canvas
RAIL_BOTTOM = 1010              # 40px of air above the receipt
HEAD_TO_RAIL = 44

DOT = 46                        # numbered marker diameter
RAIL_X = MARGIN + DOT // 2
STEP_TEXT_X = MARGIN + DOT + 30
STEP_TEXT_W = SLIDE_W - MARGIN - STEP_TEXT_X
STEP_GAP = 22
STEP_MAX_LINES = 3
LABEL_SIZE = 23
BODY_LINE_SPACING = 1.24
HEADER_MIN = 300


def _dateline(when: str) -> str:
    try:
        d = datetime.fromisoformat(when).date()
    except (ValueError, TypeError):
        d = date.today()
    return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}".upper()


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #
def _layout_steps(card: StoryCard, available: int):
    """Fit the four steps into `available` pixels, shrinking body type to suit.

    Nothing is truncated while fitting. The whole point of the format is that
    the reader gets the complete walk-through on one frame, and the step most
    likely to run long is "why it matters" - the one carrying the line a reader
    came for. Dropping its last line to make the layout work would be the layout
    quietly deciding the story is less important than the grid.

    So the type shrinks instead, and only if the smallest size still overflows
    does anything get cut, with a warning, because at that point the alternative
    is text drawn over the source strip.
    """
    label_font = fonts.label_font(LABEL_SIZE, 700)
    blocks: list = []
    total = 0
    for size in range(34, 21, -2):
        body_font = fonts.body_font(size, 400)
        blocks, total = [], 0
        for step in card.steps:
            lines = fonts.wrap_text(body_font, step.text, STEP_TEXT_W)
            lh = int(size * BODY_LINE_SPACING)
            height = fonts.line_height(label_font) + 10 + len(lines) * lh
            blocks.append((step, body_font, lines, lh, height))
            total += height + STEP_GAP
        total -= STEP_GAP
        if total <= available:
            return blocks, total

    # Last resort. The generator's character limits are worked back from this
    # budget, so reaching here means the model ignored them.
    log.warning("story card steps need %dpx at the smallest size but only %dpx "
                "is available; truncating to %d lines each",
                total, available, STEP_MAX_LINES)
    trimmed, total = [], 0
    for step, body_font, lines, lh, _height in blocks:
        lines = lines[:STEP_MAX_LINES]
        height = fonts.line_height(label_font) + 10 + len(lines) * lh
        trimmed.append((step, body_font, lines, lh, height))
        total += height + STEP_GAP
    return trimmed, max(0, total - STEP_GAP)


def _draw_rail(canvas: Image.Image, draw: ImageDraw.ImageDraw, blocks, tone, *,
               top: int) -> int:
    """The four stops, joined by a vertical rule."""
    y = top
    centres = []
    label_font = fonts.label_font(LABEL_SIZE, 700)
    for index, (step, body_font, lines, lh, height) in enumerate(blocks, 1):
        label = step.label
        cy = y + DOT // 2
        centres.append(cy)
        draw.ellipse([MARGIN, y, MARGIN + DOT, y + DOT], fill=tone)
        number = str(index)
        nb = label_font.getbbox(number)
        draw.text((MARGIN + (DOT - (nb[2] - nb[0])) // 2 - nb[0],
                   y + (DOT - (nb[3] - nb[1])) // 2 - nb[1]), number,
                  font=fonts.label_font(24, 800),
                  fill=theme.hex_to_rgb(theme.SURFACE))

        draw.text((STEP_TEXT_X, y + 2), label.upper(), font=label_font,
                  fill=theme.safe_fill(tone, LABEL_SIZE))
        ty = y + fonts.line_height(label_font) + 10
        for line in lines:
            draw.text((STEP_TEXT_X, ty), line, font=body_font,
                      fill=theme.hex_to_rgb(theme.TEXT_PRIMARY))
            ty += lh
        y += height + STEP_GAP

    if len(centres) > 1:
        draw.rectangle([RAIL_X - 1, centres[0], RAIL_X + 1, centres[-1]],
                       fill=theme.hex_to_rgb(theme.SURFACE_DEEP))
        # Redraw the markers over the rule so it passes behind them.
        for index, cy in enumerate(centres, 1):
            draw.ellipse([MARGIN, cy - DOT // 2, MARGIN + DOT, cy + DOT // 2],
                         fill=tone)
            number = str(index)
            nf = fonts.label_font(24, 800)
            nb = nf.getbbox(number)
            draw.text((MARGIN + (DOT - (nb[2] - nb[0])) // 2 - nb[0],
                       cy - DOT // 2 + (DOT - (nb[3] - nb[1])) // 2 - nb[1]),
                      number, font=nf, fill=theme.hex_to_rgb(theme.SURFACE))
    return y


def _draw_header(canvas: Image.Image, draw: ImageDraw.ImageDraw, card: StoryCard,
                 tone, *, budget: int) -> int:
    """Kicker, headline and standfirst. Returns where the copy actually ended.

    Returning the real end rather than the budget matters: the header grows and
    shrinks with the headline, so anything positioned from the budget eventually
    lands on top of the standfirst.
    """
    y = theme.draw_kicker(draw, "THE FULL STORY", x=MARGIN, y=HEAD_TOP, tone=tone)
    y += 16

    for size in range(78, 45, -4):
        font = fonts.title_font(size, 800)
        lines = fonts.wrap_text(font, card.headline, CONTENT_W)
        if len(lines) * int(size * 1.1) <= budget - 120:
            break
    lh = int(size * 1.1)
    for line in lines:
        draw.text((MARGIN, y), line, font=font,
                  fill=theme.hex_to_rgb(theme.TEXT_PRIMARY))
        y += lh

    if card.standfirst:
        y += 14
        sub_font = fonts.body_font(34, 500)
        for line in fonts.wrap_text(sub_font, card.standfirst, CONTENT_W)[:2]:
            draw.text((MARGIN, y), line, font=sub_font,
                      fill=theme.hex_to_rgb(theme.TEXT_SECONDARY))
            y += int(34 * 1.28)
    return y


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def render_story_card(card: StoryCard, out_path: Path, story=None,
                      image_loader=None) -> Path:
    """Render the card to `out_path` (PNG) and return the path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    story = story if story is not None else getattr(card, "story", None)
    tone = theme.tone_for(story, category=card.category)

    canvas = theme.paper(SLIDE_W, SLIDE_H)
    draw = ImageDraw.Draw(canvas)
    theme.draw_masthead(canvas, draw, tone=tone,
                        date_text=_dateline(card.scheduled_time))

    # Two passes, and the order matters. A first pass sizes the steps against
    # the room they would have if the header took its minimum, which gives the
    # header its budget. The header is then drawn and reports where it *actually*
    # ended - usually short of the budget - and the steps are re-fitted against
    # the space genuinely left below it.
    #
    # Laying the rail out once against the budget is what let it overrun: the
    # header ends wherever the headline does, so a rail positioned from the
    # budget rather than from the header slides down into the receipt.
    provisional = RAIL_BOTTOM - (HEAD_TOP + HEADER_MIN + HEAD_TO_RAIL)
    _blocks, rail_h = _layout_steps(card, provisional)
    header_budget = RAIL_BOTTOM - rail_h - HEAD_TO_RAIL - HEAD_TOP

    header_bottom = _draw_header(canvas, draw, card, tone, budget=header_budget)
    rail_top = header_bottom + HEAD_TO_RAIL
    blocks, rail_h = _layout_steps(card, RAIL_BOTTOM - rail_top)
    rail_end = _draw_rail(canvas, draw, blocks, tone, top=rail_top)
    if rail_end > RAIL_BOTTOM + STEP_GAP:
        log.warning("story card rail ended at %d, past its %d floor",
                    rail_end, RAIL_BOTTOM)

    # Pip sits opposite the headline, sized to the room actually left between
    # the header and the rail rather than placed at a guessed y.
    pose = theme.pose_for_story(story, "explainer") if story is not None else "read"
    band_h = rail_top - header_bottom
    if pose and band_h >= 130:
        scale = max(5, min(9, (band_h - 40) // 24))
        theme.draw_pip(canvas, pose, scale=scale,
                       x=SLIDE_W - MARGIN - 26 * scale,
                       y=header_bottom + (band_h - 24 * scale) // 2)

    if story is not None:
        theme.draw_receipt(canvas, draw, story, x=MARGIN,
                           y=SLIDE_H - RECEIPT_FROM_BOTTOM, tick_h=38,
                           label_size=30, name_size=25)
    theme.draw_footer(canvas, draw)

    canvas.convert("RGB").save(out_path, "PNG")
    card.image_file = str(out_path)
    log.info("rendered story card -> %s", out_path.name)
    return out_path
