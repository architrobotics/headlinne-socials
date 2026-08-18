"""The X cards: 1200 x 675, four layouts.

On X the post text is the hook, so the image must add something rather than
repeat it. The old card printed the headline in the tweet and again in the
picture, which wasted the strongest position on the platform.

So the card carries the *proof*:

    receipt   who reported it, named, with a tick each
    compare   two outlets, one document, two different numbers
    correct   the original claim struck through, and what was established later
    plate     one figure beside one image
    promo     the domain, when there is no story to show

The correction card is the one to lead with. It is a format no single-outlet
account can run, it is visually unmistakable, and it makes the argument for the
product without a word of marketing.

Investment here stays deliberately small: 15% of under-25s use X for news
against 42% on Instagram, so X earns volume and replies rather than bespoke art.
All five layouts reuse components built for the other surfaces.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw

from ..config import BRAND, CATEGORY_LABELS, WEBSITE
from ..logging_setup import get_logger
from ..models import TwitterPost
from . import fonts, receipt as receipt_mod, theme

log = get_logger("render.card")

# 16:9. X crops a square card in the timeline and shows this shape whole.
CARD_W, CARD_H = 1200, 675
MARGIN = 64                     # tighter than the 4:5 surfaces: less height
PIP_GUTTER = 170                # the column layouts leave clear for the sprite

_LABEL_TO_CATEGORY = {v: k for k, v in CATEGORY_LABELS.items()}


def _category_of(post: TwitterPost) -> str:
    return _LABEL_TO_CATEGORY.get(post.category, post.category) \
        if post.category in _LABEL_TO_CATEGORY else "Technology"


def _open(tone, *, eyebrow: str = "") -> tuple[Image.Image, ImageDraw.ImageDraw]:
    canvas = theme.paper(CARD_W, CARD_H)
    draw = ImageDraw.Draw(canvas)
    draw.text((MARGIN, 44), "HEADLINNE", font=fonts.title_font(26, 800),
              fill=theme.hex_to_rgb(theme.TEXT_PRIMARY))
    if eyebrow:
        draw.text((CARD_W - MARGIN, 48), eyebrow.upper(),
                  font=fonts.label_font(20, 700),
                  fill=theme.safe_fill(tone, 20), anchor="ra")
    draw.rectangle([MARGIN, 84, CARD_W - MARGIN, 87], fill=tone)
    return canvas, draw


def _close(canvas: Image.Image, draw: ImageDraw.ImageDraw,
           pose: Optional[str] = "idle") -> Image.Image:
    if pose:
        theme.draw_pip(canvas, pose, x=CARD_W - MARGIN - 26 * 7,
                       y=CARD_H - 150 - 24 * 7, scale=7)
    draw.text((MARGIN, CARD_H - 56), WEBSITE.lower(),
              font=fonts.label_font(22, 600),
              fill=theme.hex_to_rgb(theme.TEXT_SECONDARY))
    return canvas


def _headline(draw: ImageDraw.ImageDraw, text: str, *, y: int, size: int = 54,
              max_w: int | None = None, fill=None) -> int:
    font = fonts.title_font(size, 800)
    width = max_w or (CARD_W - 2 * MARGIN - 200)
    lh = int(size * 1.16)
    for line in fonts.wrap_text(font, text, width):
        draw.text((MARGIN, y), line, font=font,
                  fill=fill or theme.hex_to_rgb(theme.TEXT_PRIMARY))
        y += lh
    return y


# --------------------------------------------------------------------------- #
# The layouts
# --------------------------------------------------------------------------- #
def render_receipt_card(story, post: Optional[TwitterPost] = None) -> Image.Image:
    """Who reported it, and whether they agree. Every outlet named."""
    tone = theme.hex_to_rgb(theme.TONE_AGREE)
    canvas, draw = _open(tone, eyebrow="Sources")
    _headline(draw, receipt_mod.label(story), y=124, size=54)

    names = receipt_mod.outlets(story)[:8]
    font = fonts.label_font(26, 600)
    agree = theme.hex_to_rgb(theme.TONE_AGREE)
    filled, _hollow = receipt_mod.ticks(story)
    col_w = (CARD_W - 2 * MARGIN - 120) // 2
    for i, name in enumerate(names):
        col, row = divmod(i, 4)
        x = MARGIN + col * col_w
        y = 250 + row * 52
        mark = agree if i < filled else theme.hex_to_rgb(theme.TEXT_MUTED)
        if i < filled:
            draw.rectangle([x, y + 4, x + 10, y + 30], fill=mark)
        else:
            draw.rectangle([x, y + 4, x + 10, y + 30], outline=mark, width=3)
        draw.text((x + 26, y), name, font=font,
                  fill=theme.hex_to_rgb(theme.TEXT_PRIMARY))
    return _close(canvas, draw, pose=receipt_mod.POSE[receipt_mod.state(story)])


def render_compare_card(story) -> Image.Image:
    """Two outlets, one document, two numbers. The disagreement, shown."""
    tone = theme.hex_to_rgb(theme.TONE_DISPUTE)
    canvas, draw = _open(tone, eyebrow="Sources disagree")
    _headline(draw, "Same memo. Two numbers.", y=118, size=50)

    record = receipt_mod.agreement_of(story)
    pairs = [(story.source, record.claim)]
    pairs += [(c.outlet, c.value) for c in record.conflicts]
    pairs = [(o, v) for o, v in pairs if v][:2]

    # Reserve a column on the right for Pip. Without it the second panel runs
    # to the margin and the sprite lands on top of its border, which is exactly
    # the kind of fault the reel's collision trace catches and a static card
    # has to be laid out to avoid.
    panel_w = (CARD_W - 2 * MARGIN - 40 - PIP_GUTTER) // 2
    for i, (outlet, value) in enumerate(pairs):
        x = MARGIN + i * (panel_w + 40)
        y = 236
        draw.rectangle([x, y, x + panel_w, y + 190], outline=tone, width=3)
        draw.text((x + 22, y + 20), outlet.upper(),
                  font=fonts.label_font(20, 700), fill=theme.safe_fill(tone, 20))
        # The number large, what it counts small underneath. Printing the whole
        # "12,000 jobs" string twice - once as the value and once as the label -
        # says nothing the second time and reads as a rendering fault.
        number = str(value).replace(record.claim_unit, "").strip() or str(value)
        draw.text((x + 22, y + 58), number, font=fonts.title_font(64, 800),
                  fill=theme.hex_to_rgb(theme.TEXT_PRIMARY))
        draw.text((x + 22, y + 146), record.claim_unit or "reported",
                  font=fonts.body_font(24, 500),
                  fill=theme.hex_to_rgb(theme.TEXT_SECONDARY))

    draw.text((MARGIN, 462), "One counted differently. Both are on the record.",
              font=fonts.body_font(26, 500),
              fill=theme.hex_to_rgb(theme.TEXT_SECONDARY))
    theme.draw_pip(canvas, "puzzled", scale=6,
                   x=CARD_W - MARGIN - 26 * 6, y=250)
    return _close(canvas, draw, pose=None)


def render_correction_card(reported: str, established: str, *,
                           note: str = "", when: str = "") -> Image.Image:
    """The original claim struck through, and what was established later."""
    tone = theme.hex_to_rgb(theme.BRAND_TERRACOTTA)
    canvas, draw = _open(tone, eyebrow="Correction")

    label_font = fonts.label_font(20, 700)
    draw.text((MARGIN, 132), f"REPORTED {when}".strip(), font=label_font,
              fill=theme.safe_fill(tone, 20))
    struck_font = fonts.title_font(38, 700)
    draw.text((MARGIN, 166), reported, font=struck_font,
              fill=theme.hex_to_rgb(theme.TONE_LIVE))
    width = fonts.text_width(struck_font, reported)
    draw.line([(MARGIN, 190), (MARGIN + width, 190)],
              fill=theme.hex_to_rgb(theme.TONE_LIVE), width=4)

    draw.text((MARGIN, 268), "ESTABLISHED LATER", font=label_font,
              fill=theme.safe_fill(tone, 20))
    _headline(draw, established, y=302, size=40, max_w=CARD_W - 2 * MARGIN - 180)

    if note:
        draw.text((MARGIN, 470), note, font=fonts.body_font(26, 500),
                  fill=theme.hex_to_rgb(theme.TEXT_SECONDARY))
    return _close(canvas, draw, pose="read")


def render_plate_card(story, loader=None) -> Image.Image:
    """One figure beside one image."""
    from . import plate as plate_mod

    tone = theme.tone_for(story, category=getattr(story, "category", ""))
    canvas, draw = _open(tone, eyebrow=getattr(story, "category", "") or "Brief")

    plate_img, _rung = plate_mod.for_story(story, loader, width=420, height=280)
    if plate_img is not None:
        canvas.alpha_composite(plate_img,
                               (CARD_W - MARGIN - plate_img.width, 130))
        text_w = CARD_W - 2 * MARGIN - plate_img.width - 40
    else:
        text_w = CARD_W - 2 * MARGIN - 200

    _headline(draw, story.title, y=140, size=44, max_w=text_w)
    theme.draw_receipt(canvas, draw, story, x=MARGIN, y=CARD_H - 210,
                       tick_h=32, label_size=26, name_size=22, short=True)
    return _close(canvas, draw, pose=None if plate_img is not None else "carry")


def render_promo_card(post: TwitterPost) -> Image.Image:
    """The domain, when there is no story to show."""
    tone = theme.hex_to_rgb(theme.BRAND_TERRACOTTA)
    canvas, draw = _open(tone, eyebrow="Read it")
    _headline(draw, post.lead or WEBSITE.lower(), y=140, size=64)
    draw.text((MARGIN, 300),
              f"{BRAND} shows you every source on a story, side by side.",
              font=fonts.body_font(28, 500),
              fill=theme.hex_to_rgb(theme.TEXT_SECONDARY))
    draw.text((MARGIN, 344), "Free to read. No account needed.",
              font=fonts.body_font(28, 500),
              fill=theme.hex_to_rgb(theme.TEXT_SECONDARY))
    return _close(canvas, draw, pose="carry")


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def choose_layout(post: TwitterPost, story=None) -> str:
    """Which card a post earns.

    The disagreement layouts win whenever they apply, because they are the ones
    only this product can run.
    """
    if post.kind == "promo" or story is None:
        return "promo"
    state = receipt_mod.state(story)
    if state == "disputed" and receipt_mod.agreement_of(story).conflicts:
        return "compare"
    if receipt_mod.agreement_of(story).reported >= 4:
        return "receipt"
    return "plate"


def render_twitter_card(post: TwitterPost, out_path: Path, story=None,
                        image_loader=None) -> Path:
    """Render a post's card to `out_path` (PNG) and return the path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    layout = choose_layout(post, story)
    if layout == "promo":
        img = render_promo_card(post)
    elif layout == "compare":
        img = render_compare_card(story)
    elif layout == "receipt":
        img = render_receipt_card(story, post)
    else:
        img = render_plate_card(story, image_loader)
    img.convert("RGB").save(out_path, "PNG")
    post.image_file = str(out_path)
    log.info("rendered X %s card -> %s", layout, out_path.name)
    return out_path
