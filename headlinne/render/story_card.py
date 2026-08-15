"""The daily story card: one article, start to finish, on one image.

A carousel asks a reader to swipe, which means every slide is another chance for
them to leave. This format asks for something different. Everything is on one
frame, so the natural response is not to page through it but to keep it, and a
save is worth far more to a post's reach than a swipe is.

The layout is design/prototypes/cards.py: a kicker naming what the reader is
looking at, one headline carrying the whole claim, and the receipt strip showing
who reported it. There is no body copy and no photograph - what the card offers
is a claim and the evidence for it, which is the one thing a feed of headlines
cannot.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageDraw

from types import SimpleNamespace

from ..config import (INK, SLIDE_H, SLIDE_W, SURFACE, SURFACE_DEEP,
                      TEXT_SECONDARY, WEBSITE)
from ..logging_setup import get_logger
from ..models import StoryCard
from . import fonts, slides, theme
from . import receipt as _receipt

log = get_logger("render.story_card")

ImageLoader = Callable[[Optional[str]], Optional[Image.Image]]

MARGIN = theme.MARGIN
# far less on the frame and the extra air is what makes it read as a keepsake.
CARD_MARGIN = 84

# The three cards, from design/prototypes/cards.py. The kicker names what the
# reader is looking at, the accent carries the temperature, and the pose says
# the same thing again for anyone who reads the character before the words.
CARD_KINDS = {
    "brief":    ("Your brief",       "carry",   (196, 86, 47)),
    "breaking": ("Developing",       "alert",   (232, 74, 42)),
    "disagree": ("Sources disagree", "puzzled", (255, 180, 61)),
}

# The rail may never eat into it: it shrinks its own type instead. Both blocks
# have a floor, and between them they are what makes the character limits in
# generate/story_card.py the numbers they are.


def _dateline(scheduled_time: str) -> str:
    try:
        day = datetime.fromisoformat(scheduled_time).date()
    except (TypeError, ValueError):
        day = date.today()
    # "TUE 15 AUG" - the design's dateline carries no comma and no leading
    # zero, so it reads as a stamp rather than as a sentence.
    return f"{day.strftime('%a')} {day.day} {day.strftime('%b')}".upper()


def _rgb(value: str) -> tuple[int, int, int]:
    return theme.hex_to_rgb(value)


def _card_kind(card: StoryCard) -> tuple[str, str | None, tuple[int, int, int]]:
    """The kicker, Pip's pose and the accent for this card.

    A sensitive story keeps its kicker and its accent but loses the mascot -
    theme.pose_for is the single place that judgement lives.
    """
    kicker, _, tone = CARD_KINDS.get(card.kind, CARD_KINDS["brief"])
    # pose_for already maps brief -> carry, breaking -> alert, disagree ->
    # puzzled, which is the prototype's mapping. Ask it by kind, not by pose.
    pose = theme.pose_for(card.kind,
                          sensitive=bool(getattr(card, "sensitive", False)))
    return kicker, pose, tone


def _receipt_source(card: StoryCard):
    """What render/receipt.py needs, which is the outlets rather than a string.

    receipt.py reads .source and .corroborating_sources off a Story. The card
    carries the flattened list, so hand it back in the shape the strip expects
    rather than teaching the strip a second input.
    """
    names = list(card.outlets)
    return SimpleNamespace(source=names[0] if names else "",
                           corroborating_sources=names[1:],
                           verified=len(names) > 1)


def render_story_card(card: StoryCard, out_path: Path,
                      image_loader: ImageLoader | None = None) -> Path:
    """Render the day's story card to a PNG and stamp the path onto the card.

    The layout is the one worked out in design/prototypes/cards.py: wordmark and
    date over a single hairline, Pip at a fixed size and place, a kicker, the
    headline, and the receipt strip doing the arguing at the foot. There is no
    numbered rail and no photograph - the card is the counterweight to the
    carousel, and what it offers is a claim and the evidence for it.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    kicker, pose, tone = _card_kind(card)
    canvas = Image.new("RGBA", (SLIDE_W, SLIDE_H), _rgb(SURFACE))
    draw = ImageDraw.Draw(canvas)
    ink, ink_soft = _rgb(INK), _rgb(TEXT_SECONDARY)
    m = CARD_MARGIN

    # Header: wordmark left, date right. One hairline, no pills.
    draw.text((m, 74), "HEADLINNE", font=fonts.title_font(34, 800), fill=ink)
    draw.text((SLIDE_W - m, 78), _dateline(card.scheduled_time).upper(),
              font=fonts.label_font(26, 600), fill=ink_soft, anchor="ra")
    draw.rectangle([m, 132, SLIDE_W - m, 136], fill=tone)

    # Pip, always the same size and always the same place - he is furniture the
    # reader learns, not a decoration that moves with the copy. Sensitive
    # stories carry no mascot at all.
    if pose:
        theme.draw_pip(canvas, pose, x=m - 30, y=196, scale=15)

    draw.text((m, 606), kicker.upper(), font=fonts.label_font(30, 700), fill=tone)

    headline_font = fonts.title_font(84, 800)
    y = 664
    for line in fonts.wrap_text(headline_font, card.headline, SLIDE_W - m * 2):
        draw.text((m, y), line, font=headline_font, fill=ink)
        y += 96

    # The receipt strip does the arguing. This is the prototype's strip rather
    # than theme.draw_receipt: that one reports how many outlets covered the
    # story and cannot say how many of them agree, which is exactly what the
    # disagree card exists to show.
    n = len(card.outlets)
    agree = card.agree if card.agree else n
    ry = SLIDE_H - 322
    slides.receipt_strip(draw, m, ry, n, agree)
    draw.text((m, ry + 74), f"{agree} of {n} outlets agree",
              font=fonts.label_font(34, 700), fill=ink)
    draw.text((m, ry + 122), _receipt.named(_receipt_source(card), limit=3),
              font=fonts.label_font(28, 500), fill=ink_soft)

    draw.rectangle([m, SLIDE_H - 132, SLIDE_W - m, SLIDE_H - 130],
                   fill=_rgb(SURFACE_DEEP))
    draw.text((m, SLIDE_H - 108), WEBSITE.lower(),
              font=fonts.label_font(26, 600), fill=ink_soft)

    canvas.convert("RGB").save(out_path, "PNG")
    card.image_file = str(out_path)
    log.info("rendered story card (%s, %d outlets) -> %s",
             card.kind, len(card.outlets), out_path.name)
    return out_path
