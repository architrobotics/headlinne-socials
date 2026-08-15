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
from .carousel import _lead_number
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
                      image_loader: ImageLoader | None = None) -> list[Path]:
    """Render the day's story as its own carousel, returning the slide paths.

    One story, walked all the way through: a cover that states it, a page for
    the thing the reader did not know, a close showing who reported it, and the
    ask. It is the counterweight to the twice-weekly brief - that one is many
    stories a page each, this one is a single story given room.

    `out_path` may be a file or a directory; the slides are written beside it
    either way, and the first is stamped onto the card as its cover.
    """
    out_dir = out_path if out_path.suffix == "" else out_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    kicker, pose, tone = _card_kind(card)
    dateline = _dateline(card.scheduled_time)
    agree, total = slides.display_ratio(card.agree or len(card.outlets),
                                        len(card.outlets))
    named = _receipt.named(_receipt_source(card), limit=3)

    # The designed set is five: state it, size it, turn it, show the working,
    # ask. Every page is always drawn - a set that is sometimes three and
    # sometimes five stops being a format the audience recognises.
    number = _lead_number(card.headline) or _lead_number(card.standfirst)
    # Never say the headline twice. A five-page set whose middle pages repeat
    # the cover is worse than three pages, because the reader keeps swiping to
    # find the part that is new.
    caption_line = (card.caption or "").splitlines()[0].strip() \
        if card.caption else ""
    second = card.standfirst or caption_line
    third = caption_line if caption_line != second else ""
    if not third:
        third = (f"{agree} of {total} outlets reported the same thing."
                 if total else "")
    pages = [
        slides.slide_cover(
            kicker=kicker, headline=card.headline,
            standfirst=card.standfirst, dateline=dateline,
            say=card.standfirst or None, sources=total, agree=agree,
            tone=tone, pose=pose),
    ]
    if number:
        pages.append(slides.slide_scale(
            kicker="How big", number=number[0], unit=number[1],
            body=card.standfirst or card.caption.split("\n")[0],
            dateline=dateline, say=slides.pip_line("scale"), pose="read"))
    else:
        pages.append(slides.slide_brief(
            kicker="What happened", headline=second or card.headline,
            standfirst="", dateline=dateline, sources=total, agree=agree,
            pose="read"))
    pages.append(slides.slide_twist(
        kicker="Why it matters",
        headline=card.standfirst or card.headline,
        body=card.caption.split("\n")[0] if card.caption else "",
        dateline=dateline, say=slides.pip_line("twist"), pose="puzzled"))
    pages.append(slides.slide_close(
        outlets=named, body="Headlinne reads every outlet covering a story and "
                            "shows you where they agree, and where they don't.",
        dateline=dateline, say=slides.pip_line("close", agree=agree, total=total),
        sources=total, agree=agree, pose=pose))
    pages.append(slides.slide_cta(
        body="Every source on this story, side by side. Free to read, no "
             "account needed.",
        dateline=dateline, say=slides.pip_line("cta"), sources=total,
        agree=agree, pose=pose))

    paths: list[Path] = []
    for i, page in enumerate(pages, 1):
        path = out_dir / f"slide_{i}.png"
        page.convert("RGB").save(path, "PNG")
        paths.append(path)
    card.image_file = str(paths[0])
    log.info("rendered story carousel (%s, %d pages, %d of %d agree) -> %s",
             card.kind, len(paths), agree, total, out_dir.name)
    return paths
