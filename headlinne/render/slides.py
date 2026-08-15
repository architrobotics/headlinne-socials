"""The carousel slides, ported from design/prototypes/formats.py.

Five slides doing five different jobs rather than five variations of one layout:
a cover that states the event, a scale slide that makes a number mean something,
a twist that gives the reader the thing they did not know, a close that shows
the sourcing, and a CTA that asks. The furniture - header rule, speech bubble,
receipt strip, footer - is shared so the set reads as one system.

Geometry, type sizes and colours are the prototype's. Where the package already
owns a component (Pip, the fonts) this calls it rather than redrawing it.
"""

from __future__ import annotations

import re
from typing import Sequence

from PIL import Image, ImageDraw

from ..config import (INK, SLIDE_H, SLIDE_W, SURFACE, SURFACE_DEEP,
                      TEXT_MUTED, TEXT_SECONDARY, WEBSITE)
from . import fonts, theme

MARGIN = 84                     # the design's margin, wider than the old one

# The prototype's palette. The four category accents live in config; these are
# the two the slides add - a coral hot enough for a developing story, and the
# bubble's cream, which is warmer than the page so it reads as raised.
CORAL = (206, 62, 34)
CREAM = (245, 239, 228)
NIGHT = (23, 18, 14)
DARK_RULE = (58, 48, 39)
DARK_SUB = (168, 154, 137)


def _rgb(value: str) -> tuple[int, int, int]:
    return theme.hex_to_rgb(value)


def font(px: int, weight: int = 800):
    """The prototype's single face: Manrope on its weight axis."""
    return fonts.label_font(px, weight)


def block(draw: ImageDraw.ImageDraw, text: str, fnt, x: int, y: int,
          max_w: int, lh: int, fill) -> int:
    """Wrapped text on a fixed leading. Returns the y below the last line."""
    for line in fonts.wrap_text(fnt, text, max_w):
        draw.text((x, y), line, font=fnt, fill=fill)
        y += lh
    return y


def bubble(canvas: Image.Image, draw: ImageDraw.ImageDraw, text: str,
           x: int, y: int, max_w: int, *, tail: str = "left",
           fill=CREAM, ink=None, size: int = 34) -> int:
    """Comic speech bubble with a pixel-stepped edge and a tail toward Pip.

    The stepped tail is drawn as one polygon rather than three rectangles so it
    stays in the same pixel language as Pip and reads as a shape.
    """
    ink = ink if ink is not None else _rgb(INK)
    fnt = font(size, 650)
    lines = fonts.wrap_text(fnt, text, max_w - 44)
    text_w = max(draw.textlength(line, font=fnt) for line in lines)
    w = int(text_w) + 44
    h = len(lines) * int(size * 1.34) + 34

    draw.rectangle([x, y, x + w, y + h], fill=fill)
    for off in (0, 3):                                  # chunky pixel border
        draw.rectangle([x - off, y - off, x + w + off, y + h + off],
                       outline=ink, width=3)
    ty = y + 17
    for line in lines:
        draw.text((x + 22, ty), line, font=fnt, fill=ink)
        ty += int(size * 1.34)

    s, b = 11, y + h
    bx = x + 34 if tail == "left" else x + w - 34 - 3 * s
    pts = [(bx, b), (bx + 3 * s, b)]
    for i in range(3):                       # descending staircase on one side
        pts += [(bx + (3 - i) * s, b + (i + 1) * s),
                (bx + (2 - i) * s, b + (i + 1) * s)]
    draw.polygon(pts, fill=fill)
    draw.line(pts[1:] + [pts[0]], fill=ink, width=3, joint="curve")
    draw.rectangle([bx + 2, b - 3, bx + 3 * s - 2, b + 2], fill=fill)
    return h


def receipt_strip(draw: ImageDraw.ImageDraw, x: int, y: int, n: int, agree: int,
                  *, w: int = 13, h: int = 46, gap: int = 9, on=None, off=None):
    """One tick per outlet, filled where corroborated."""
    on = on if on is not None else theme.accent_for("Finance")
    off = off if off is not None else _rgb(TEXT_SECONDARY)
    for i in range(n):
        bx = x + i * (w + gap)
        if i < agree:
            draw.rectangle([bx, y, bx + w, y + h], fill=on)
        else:
            draw.rectangle([bx, y, bx + w, y + h], outline=off, width=3)


def header(draw: ImageDraw.ImageDraw, dateline: str, tone, *,
           w: int = SLIDE_W, m: int = MARGIN, dark: bool = False) -> None:
    """Wordmark left, date right, one hairline rule in the slide's accent."""
    fg = CREAM if dark else _rgb(INK)
    sub = DARK_SUB if dark else _rgb(TEXT_SECONDARY)
    draw.text((m, 74), "HEADLINNE", font=font(34, 800), fill=fg)
    draw.text((w - m, 78), dateline.upper(), font=font(26, 600), fill=sub,
              anchor="ra")
    draw.rectangle([m, 132, w - m, 136], fill=tone)


def footer(draw: ImageDraw.ImageDraw, *, w: int = SLIDE_W, h: int = SLIDE_H,
           m: int = MARGIN, dark: bool = False) -> None:
    draw.rectangle([m, h - 132, w - m, h - 130],
                   fill=DARK_RULE if dark else _rgb(SURFACE_DEEP))
    # The design sets the domain in lower case wherever it appears - it reads
    # as a URL that way rather than as a second wordmark competing with the one
    # at the top of the slide.
    draw.text((m, h - 108), WEBSITE.lower(), font=font(26, 600),
              fill=DARK_SUB if dark else _rgb(TEXT_SECONDARY))


def _page(tone, dateline: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    canvas = Image.new("RGBA", (SLIDE_W, SLIDE_H), _rgb(SURFACE))
    draw = ImageDraw.Draw(canvas)
    header(draw, dateline, tone)
    return canvas, draw


# --------------------------------------------------------------------------- #
# The five slides
# --------------------------------------------------------------------------- #
def slide_cover(*, kicker: str, headline: str, standfirst: str, dateline: str,
                say: str | None = None, sources: int = 0, agree: int = 0,
                tone=CORAL, pose: str | None = "alert") -> Image.Image:
    """States the event. Pip reacts to it; the receipt says who else saw it."""
    canvas, draw = _page(tone, dateline)
    m, ink = MARGIN, _rgb(INK)
    if pose:
        theme.draw_pip(canvas, pose, x=m - 34, y=210, scale=16)
        if say:
            bubble(canvas, draw, say, m + 400, 262, 540)
    draw.text((m, 640), kicker.upper(), font=font(30, 700), fill=tone)
    block(draw, headline, font(92, 800), m, 698, SLIDE_W - m * 2, 104, ink)
    draw.text((m, 918), standfirst, font=font(42, 500), fill=_rgb(TEXT_SECONDARY))
    if sources:
        receipt_strip(draw, m, SLIDE_H - 300, sources, agree)
        draw.text((m, SLIDE_H - 226), f"{agree} of {sources} outlets agree",
                  font=font(32, 700), fill=ink)
    footer(draw)
    return canvas


def slide_scale(*, kicker: str, number: str, unit: str, body: str,
                dateline: str, say: str | None = None, tone=None,
                pose: str | None = "read") -> Image.Image:
    """Makes one number mean something. The numeral is the whole slide."""
    tone = tone if tone is not None else theme.accent_for("Technology")
    canvas, draw = _page(tone, dateline)
    m, ink = MARGIN, _rgb(INK)
    draw.text((m, 220), kicker.upper(), font=font(30, 700), fill=tone)
    numeral = font(280, 800)
    draw.text((m, 274), number, font=numeral, fill=ink)
    # The unit sits after the numeral rather than at a fixed offset: "4" and
    # "8,700" are not the same width, and the prototype only ever drew "4".
    # Keep the design's position for a single digit, and push past the
    # numeral only when it is wider than that allowed for.
    unit_x = max(m + 300, m + int(draw.textlength(number, font=numeral)) + 28)
    draw.text((unit_x, 420), unit, font=font(64, 700), fill=ink)
    block(draw, body, font(46, 500), m, 620, SLIDE_W - m * 2, 60,
          _rgb(TEXT_SECONDARY))
    if pose:
        theme.draw_pip(canvas, pose, x=SLIDE_W - m - 320, y=SLIDE_H - 560,
                       scale=12)
        if say:
            bubble(canvas, draw, say, m, SLIDE_H - 480, 520)
    footer(draw)
    return canvas


def slide_twist(*, kicker: str, headline: str, body: str, dateline: str,
                say: str | None = None, tone=None,
                pose: str | None = "puzzled") -> Image.Image:
    """The thing the reader did not know. The reason the carousel is saved."""
    tone = tone if tone is not None else theme.accent_for("Geopolitics")
    canvas, draw = _page(tone, dateline)
    m, ink = MARGIN, _rgb(INK)
    if pose:
        theme.draw_pip(canvas, pose, x=m - 30, y=200, scale=15)
        if say:
            bubble(canvas, draw, say, m + 380, 250, 520)
    draw.text((m, 610), kicker.upper(), font=font(30, 700), fill=tone)
    block(draw, headline, font(78, 800), m, 668, SLIDE_W - m * 2, 92, ink)
    block(draw, body, font(38, 500), m, SLIDE_H - 400, SLIDE_W - m * 2, 52,
          _rgb(TEXT_SECONDARY))
    footer(draw)
    return canvas


def slide_close(*, outlets: str, body: str, dateline: str,
                say: str | None = None, sources: int = 0, agree: int = 0,
                tone=None, pose: str | None = "verified") -> Image.Image:
    """Shows the working. The receipt is the argument, not decoration."""
    tone = tone if tone is not None else theme.accent_for("Finance")
    canvas, draw = _page(tone, dateline)
    m, ink = MARGIN, _rgb(INK)
    if pose:
        theme.draw_pip(canvas, pose, x=m - 34, y=210, scale=16)
        if say:
            bubble(canvas, draw, say, m + 400, 262, 520)
    draw.text((m, 660), "SOURCES", font=font(30, 700), fill=tone)
    if sources:
        receipt_strip(draw, m, 720, sources, agree)
    draw.text((m, 800), outlets, font=font(34, 600), fill=ink)
    block(draw, body, font(40, 500), m, 900, SLIDE_W - m * 2, 54,
          _rgb(TEXT_SECONDARY))
    footer(draw)
    return canvas


def slide_brief(*, kicker: str, headline: str, standfirst: str, dateline: str,
                index: int = 0, of: int = 0, sources: int = 0, agree: int = 0,
                tone=None, pose: str | None = None) -> Image.Image:
    """One story, one page. The unit of the twice-weekly brief.

    A brief page is not a smaller cover: it carries no mascot and no bubble,
    because a reader is moving through several of these and a character
    reacting on every one stops being a reaction. What each page does carry is
    its own receipt - the sourcing belongs to the story, not to the set.
    """
    tone = tone if tone is not None else theme.accent_for("Technology")
    canvas, draw = _page(tone, dateline)
    m, ink = MARGIN, _rgb(INK)

    # Pip changes pose page to page. He is the thread through the set - the
    # thing that makes five unrelated stories read as one brief - so he is
    # present, but small and low, where he cannot compete with the headline.
    if pose:
        pw, ph = theme.pip_size(pose, 9)
        theme.draw_pip(canvas, pose, x=SLIDE_W - m - pw, y=SLIDE_H - 300 - ph,
                       scale=9)

    draw.text((m, 262), kicker.upper(), font=font(30, 700), fill=tone)
    if of:
        draw.text((SLIDE_W - m, 262), f"{index} / {of}", font=font(30, 700),
                  fill=_rgb(TEXT_MUTED), anchor="ra")
    y = block(draw, headline, font(76, 800), m, 330, SLIDE_W - m * 2, 88, ink)
    if standfirst:
        block(draw, standfirst, font(38, 500), m, y + 26, SLIDE_W - m * 2, 52,
              _rgb(TEXT_SECONDARY))
    if sources:
        receipt_strip(draw, m, SLIDE_H - 300, sources, agree)
        draw.text((m, SLIDE_H - 226), f"{agree} of {sources} outlets agree",
                  font=font(32, 700), fill=ink)
    footer(draw)
    return canvas


def slide_cta(*, body: str, dateline: str, say: str | None = None,
              sources: int = 0, agree: int = 0, tone=None,
              pose: str | None = "carry") -> Image.Image:
    """Last slide of every carousel. Pip asks; the domain is the loudest thing."""
    tone = tone if tone is not None else theme.accent_for("Technology")
    canvas, draw = _page(tone, dateline)
    m, ink = MARGIN, _rgb(INK)
    if pose:
        theme.draw_pip(canvas, pose, x=m - 34, y=236, scale=16)
        if say:
            bubble(canvas, draw, say, m + 400, 288, 520)
    draw.text((m, 700), "READ THE FULL STORY", font=font(30, 700), fill=tone)
    block(draw, WEBSITE.lower(), font(104, 800), m, 754, SLIDE_W - m * 2, 116, ink)
    block(draw, body, font(40, 500), m, 908, SLIDE_W - m * 2, 54,
          _rgb(TEXT_SECONDARY))
    if sources:
        receipt_strip(draw, m, SLIDE_H - 300, sources, agree)
        draw.text((m, SLIDE_H - 226), f"{agree} of {sources} outlets agree",
                  font=font(32, 700), fill=ink)
    footer(draw)
    return canvas


# --------------------------------------------------------------------------- #
# Reading the receipt out of generated content
# --------------------------------------------------------------------------- #
_OVERFLOW = re.compile(r"\+\s*(\d+)\s*$")


def source_counts(sources: str, outlets: Sequence[str] = (),
                  agree: int = 0) -> tuple[int, int]:
    """(total, agreeing) outlets for the receipt strip.

    Prefers the structured list when the generator supplied one. Otherwise it
    reads the display line, which is written as "Reuters · BBC +2" - the named
    outlets plus an honest overflow. Returning (0, 0) is meaningful: the strip
    is then not drawn at all, which is better than drawing a confident row of
    ticks for a story whose sourcing we cannot count.
    """
    if outlets:
        total = len(outlets)
        return total, (agree or total)
    line = (sources or "").strip()
    if not line:
        return 0, 0
    extra = 0
    m = _OVERFLOW.search(line)
    if m:
        extra = int(m.group(1))
        line = line[:m.start()]
    named = [p for p in re.split(r"[·,]", line) if p.strip()]
    total = len(named) + extra
    return (total, agree or total) if total else (0, 0)


# The strip is a claim about our sourcing, so it has to be readable at a glance
# as well as true. Eight is where a row of ticks stops being countable.
MAX_TICKS = 8


def display_ratio(agree: int, total: int, cap: int = MAX_TICKS) -> tuple[int, int]:
    """The (agreeing, of) to draw, which is not always the raw pair.

    Two things distort the raw numbers. A story carried by twenty outlets fills
    a strip nobody can count, and "4 of 12" reads as a story that failed rather
    than one where four outlets independently confirmed the same thing and the
    rest were covering a different angle. So the strip shows the agreement it
    found against the sources that bear on it: everything agreeing when it all
    does, and otherwise the agreeing set plus the one that did not.

    It never inflates the agreeing count, and it never claims unanimity that is
    not there - 4 of 12 becomes 4 of 5, never 5 of 5.
    """
    agree = max(0, int(agree))
    total = max(agree, int(total))
    if agree >= total:
        n = min(total, cap)
        return n, n
    return min(agree, cap), min(agree + 1, cap)


# Pip's lines are owned by the code, the same way the hooks rotation is: they
# are the character's voice rather than the story's, so the model never writes
# them and a month of posts cannot drift into a different personality.
def pip_line(kind: str, *, agree: int = 0, total: int = 0) -> str | None:
    if kind == "twist":
        return "Here's the bit I love."
    if kind == "close":
        return f"I read all {total}. They agree." if agree >= total > 0 else \
               "I read them all. Most agree."
    if kind == "cta":
        return "Come and read it."
    if kind == "scale":
        return "That is the part worth keeping."
    return None


# The brief's pose rotation. Five stories, five attitudes, so the set has a
# rhythm rather than five copies of one drawing.
BRIEF_POSES = ("read", "point", "puzzled", "present", "carry")
