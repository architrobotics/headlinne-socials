"""The design system: the paper ground, the furniture, and the drawing verbs.

Every rendered surface - carousel slide, story card, X card, reel frame - is
built from this file, so a reel and a carousel read as one brand rather than as
two layouts that happen to share a logo.

The ground is paper. Every post used to sit on near-black, which made the
profile grid read as one dark smudge and put the brand's warm terracotta
identity on a surface that fought it. Feed presence comes from contrast at the
edge of the post, and warm paper against Instagram's white chrome separates
cleanly while looking like something printed rather than something generated.

The measurements here are not approximate. They are the ones
design/prototypes/formats.py and draft.py rendered the approved samples from,
transcribed. Changing one changes what the samples mean, so each is stated once
and every caller derives from it.

Two rules the type obeys everywhere:

  * accents that fail 4.5:1 on paper are display-only. Terracotta measures
    3.96:1 and coral 4.31:1 - both clear the 3.0 large-text floor and neither
    clears the body-copy one. `safe_fill` enforces that by size rather than
    leaving it to a comment, because the sample palette is fixed and the only
    remaining lever is where each colour is allowed to appear.
  * nothing on a reel renders below y=1450. Instagram's caption block, handle,
    audio strip and action rail sit exactly there.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter

from ..config import (BRAND_TERRACOTTA, CATEGORY_COLORS, CATEGORY_PILL, CREAM,
                      DISPLAY_ONLY_ACCENTS, DISPLAY_ONLY_MIN_PX, INK, INK_SOFT,
                      LOGO_PATH, NIGHT, SURFACE, SURFACE_DEEP, SURFACE_RAISED,
                      TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, TONE_AGREE,
                      TONE_DISPUTE, TONE_LIVE)
from . import fonts, pip as _pip, receipt as _receipt

# --------------------------------------------------------------------------- #
# Layout constants
# --------------------------------------------------------------------------- #
MARGIN = 84                 # left / right safe margin, on every canvas

MASTHEAD_Y = 74             # wordmark baseline
MASTHEAD_RULE_Y = 132       # the tone rule under it
MASTHEAD_RULE_H = 4

FOOTER_RULE_FROM_BOTTOM = 132
FOOTER_TEXT_FROM_BOTTOM = 108

# Instagram's own UI owns everything below this on a 1080x1920 canvas.
REEL_SAFE_BOTTOM = 1450


# --------------------------------------------------------------------------- #
# Colour
# --------------------------------------------------------------------------- #
def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgba(value, alpha: int = 255) -> tuple[int, int, int, int]:
    """Accept a hex string or an rgb tuple and return an rgba tuple."""
    r, g, b = hex_to_rgb(value) if isinstance(value, str) else value[:3]
    return (r, g, b, alpha)


def scale(rgb, factor: float) -> tuple[int, int, int]:
    r, g, b = rgb[:3]
    return tuple(max(0, min(255, int(c * factor))) for c in (r, g, b))  # type: ignore[return-value]


def mix(a, b, t: float) -> tuple[int, int, int]:
    """Linear blend between two rgb colours, t in [0, 1]."""
    ar, ag, ab = a[:3]
    br, bg, bb = b[:3]
    return (int(ar + (br - ar) * t), int(ag + (bg - ag) * t),
            int(ab + (bb - ab) * t))


def _relative_luminance(rgb) -> float:
    def channel(v: float) -> float:
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg, bg) -> float:
    """WCAG contrast, used by the visual quality gate and by safe_fill."""
    fg = hex_to_rgb(fg) if isinstance(fg, str) else fg
    bg = hex_to_rgb(bg) if isinstance(bg, str) else bg
    hi, lo = sorted((_relative_luminance(fg), _relative_luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


_DISPLAY_ONLY = {hex_to_rgb(c) for c in DISPLAY_ONLY_ACCENTS}


def safe_fill(colour, size_px: int):
    """The colour to actually draw with, given the size it will be drawn at.

    Terracotta and coral are part of the approved samples and are not going to
    change, but at body-copy sizes they do not clear 4.5:1 on paper. Rather than
    alter the palette - which would break sample fidelity - they are restricted
    to display sizes and fall back to ink below the threshold.
    """
    rgb = hex_to_rgb(colour) if isinstance(colour, str) else tuple(colour[:3])
    if rgb in _DISPLAY_ONLY and size_px < DISPLAY_ONLY_MIN_PX:
        return hex_to_rgb(INK)
    return rgb


def accent_for(category: str) -> tuple[int, int, int]:
    """The category's colour. Taxonomy, not meaning - see tone_for."""
    return hex_to_rgb(CATEGORY_COLORS.get(category, BRAND_TERRACOTTA))


# The tone each slide takes from the job it does, transcribed from the approved
# carousel sheet. Colour tracks *meaning* here, not taxonomy: the twist slide is
# marigold because it is a surprise, and the sources slide is mint because that
# is what agreement looks like everywhere else in the system. A reader learns
# these four associations once and then reads them without effort.
SLIDE_TONE = {
    "cover": TONE_LIVE,             # coral: this is the live one
    "scale": BRAND_TERRACOTTA,
    "twist": TONE_DISPUTE,          # marigold: the thing you did not know
    "sources": TONE_AGREE,          # mint: they agree
    "cta": BRAND_TERRACOTTA,
    # Reel beats. The same four associations, applied to the jobs a beat does,
    # which is what gives a reel the colour rhythm the approved draft has:
    # it opens coral, settles into terracotta, goes marigold on the surprising
    # figure, and closes mint on the sourcing.
    "hook": TONE_LIVE,
    "point": BRAND_TERRACOTTA,
    "graphic": TONE_DISPUTE,
    "payoff": TONE_DISPUTE,
    "outro": BRAND_TERRACOTTA,
}


def tone_for(story=None, category: str = "", role: str = "") -> tuple[int, int, int]:
    """The colour the masthead rule and kicker take.

    Semantic first, taxonomic last. What a reader most needs from a glance is
    whether the sources agree, not which desk filed it, so a disputed story is
    marigold whatever its category and a sensitive one drops to plain ink. Only
    when neither applies does the slide's own job, and then the category, decide.
    """
    if story is not None:
        if getattr(story, "sensitive", False):
            return hex_to_rgb(INK_SOFT)
        if _receipt.state(story) in ("disputed", "single"):
            return hex_to_rgb(TONE_DISPUTE)
        category = category or getattr(story, "category", "")
    if role in SLIDE_TONE:
        return hex_to_rgb(SLIDE_TONE[role])
    return accent_for(category)


def label_for(category: str) -> str:
    return CATEGORY_PILL.get(category, category.upper())


# --------------------------------------------------------------------------- #
# Grounds
# --------------------------------------------------------------------------- #
def paper(w: int, h: int) -> Image.Image:
    """A flat paper ground.

    No gradient. The old radial one was visible enough to read as a compression
    artefact rather than as lighting.
    """
    return Image.new("RGBA", (w, h), rgba(hex_to_rgb(SURFACE)))


def night(w: int, h: int) -> Image.Image:
    """The dark ground, for the rare surface that wants one."""
    return Image.new("RGBA", (w, h), rgba(hex_to_rgb(NIGHT)))


def cover_fit(img: Image.Image, w: int, h: int) -> Image.Image:
    """Scale and centre-crop a photo to exactly w x h, then sharpen.

    Shared by every surface that uses photography - carousel plates, reel
    plates, the story card - so photographs are treated identically everywhere.
    """
    img = img.convert("RGB")
    src_w, src_h = img.size
    factor = max(w / src_w, h / src_h)
    new = (max(1, int(src_w * factor)), max(1, int(src_h * factor)))
    img = img.resize(new, Image.LANCZOS)
    left = (img.width - w) // 2
    top = (img.height - h) // 2
    img = img.crop((left, top, left + w, top + h))
    if factor > 1.05:                      # upscaled sources need more help
        img = img.filter(ImageFilter.UnsharpMask(radius=2.2, percent=135, threshold=2))
    else:
        img = img.filter(ImageFilter.UnsharpMask(radius=1.1, percent=75, threshold=3))
    return img.convert("RGBA")


@lru_cache(maxsize=16)
def logo_mark(size: int) -> Optional[Image.Image]:
    """The app tile, resized (cached). None if the asset is absent.

    Nothing in the current system draws this: the wordmark carries the brand and
    Pip carries the personality. It survives for the app-store surfaces.
    """
    try:
        if LOGO_PATH.exists():
            return Image.open(LOGO_PATH).convert("RGBA").resize(
                (size, size), Image.LANCZOS)
    except Exception:  # pragma: no cover - asset best-effort
        pass
    return None


def alpha_ramp(h: int, stops: list[tuple[float, int]]) -> Image.Image:
    """A 1-px-wide vertical alpha ramp from (position, alpha) stops.

    Retained because render/motion.py builds its transitions from it.
    """
    stops = sorted(stops)
    col = Image.new("L", (1, h), 0)
    px = col.load()
    for y in range(h):
        t = y / max(1, h - 1)
        prev, nxt = stops[0], stops[-1]
        for i in range(len(stops) - 1):
            if stops[i][0] <= t <= stops[i + 1][0]:
                prev, nxt = stops[i], stops[i + 1]
                break
        span = (nxt[0] - prev[0]) or 1.0
        px[0, y] = int(prev[1] + (nxt[1] - prev[1]) * ((t - prev[0]) / span))
    return col


# --------------------------------------------------------------------------- #
# Furniture
# --------------------------------------------------------------------------- #
def draw_masthead(canvas: Image.Image, draw: ImageDraw.ImageDraw, *,
                  tone=None, date_text: str = "", width: int | None = None,
                  margin: int | None = None, y: int = MASTHEAD_Y,
                  progress: float | None = None, dark: bool = False) -> int:
    """Wordmark left, date right, a tone rule beneath. Returns the rule's y.

    The rule replaced the category pill. The pill was the loudest object on
    every canvas and carried the least useful information there; the rule states
    the same fact at a tenth of the volume, and doubles as the reel's progress
    bar without adding a second piece of furniture.
    """
    w = width or canvas.width
    m = MARGIN if margin is None else margin
    tone = hex_to_rgb(BRAND_TERRACOTTA) if tone is None else tone
    ink = hex_to_rgb(CREAM if dark else TEXT_PRIMARY)
    soft = (168, 154, 137) if dark else hex_to_rgb(TEXT_SECONDARY)

    draw.text((m, y), "HEADLINNE", font=fonts.title_font(34, 800), fill=ink)
    if date_text:
        draw.text((w - m, y + 4), date_text.upper(),
                  font=fonts.label_font(26, 600), fill=soft, anchor="ra")

    rule_y = MASTHEAD_RULE_Y if y == MASTHEAD_Y else y + 58
    if progress is None:
        draw.rectangle([m, rule_y, w - m, rule_y + MASTHEAD_RULE_H], fill=tone)
    else:
        # The rule becomes the completion bar. A viewer who can see how much is
        # left watches more of it, and it costs no extra element.
        draw.rectangle([m, rule_y, w - m, rule_y + MASTHEAD_RULE_H + 2],
                       fill=hex_to_rgb(SURFACE_DEEP))
        span = int((w - 2 * m) * max(0.0, min(1.0, progress)))
        if span:
            draw.rectangle([m, rule_y, m + span, rule_y + MASTHEAD_RULE_H + 2],
                           fill=tone)
    return rule_y


def draw_kicker(draw: ImageDraw.ImageDraw, text: str, *, x: int, y: int,
                tone, size: int = 30) -> int:
    """The small uppercase label above a headline. Returns the y below it."""
    if not text:
        return y
    font = fonts.label_font(size, 700)
    draw.text((x, y), text.upper(), font=font, fill=safe_fill(tone, size))
    return y + fonts.line_height(font)


def draw_footer(canvas: Image.Image, draw: ImageDraw.ImageDraw, *,
                text: str = "headlinne.com", width: int | None = None,
                height: int | None = None, margin: int | None = None,
                dark: bool = False) -> None:
    """A hairline rule and the domain, bottom left."""
    w = width or canvas.width
    h = height or canvas.height
    m = MARGIN if margin is None else margin
    rule = hex_to_rgb("#3A3027") if dark else hex_to_rgb(SURFACE_DEEP)
    draw.rectangle([m, h - FOOTER_RULE_FROM_BOTTOM, w - m,
                    h - FOOTER_RULE_FROM_BOTTOM + 2], fill=rule)
    draw.text((m, h - FOOTER_TEXT_FROM_BOTTOM), text,
              font=fonts.label_font(26, 600),
              fill=(168, 154, 137) if dark else hex_to_rgb(TEXT_SECONDARY))


def draw_rule(draw: ImageDraw.ImageDraw, x0: int, y: int, x1: int, *,
              thickness: int = 2, colour=None) -> int:
    draw.rectangle([x0, y, x1, y + thickness],
                   fill=colour or hex_to_rgb(SURFACE_DEEP))
    return y + thickness


# --------------------------------------------------------------------------- #
# Pip
# --------------------------------------------------------------------------- #
# Which pose a story earns. The pose is metadata, not decoration: a regular
# reader learns the kind of story from the character before reading a word.
_POSES = {
    "brief": "carry", "cover": "alert", "breaking": "alert",
    "explainer": "read", "verified": "verified", "disagree": "puzzled",
    "cta": "carry", "scale": "read", "twist": "puzzled", "sources": "verified",
}


def pose_for(story_kind: str, *, sensitive: bool = False) -> str | None:
    """Which pose a story earns, or None when it must carry no mascot at all.

    Sensitive stories - deaths, disasters - are reported plainly. Pip never
    appears beside one, and neither does a speech bubble or any wonder framing.
    Returning None rather than a neutral pose forces the caller to handle the
    absence, which is what stops a mascot appearing next to a death toll.
    """
    if sensitive:
        return None
    return _POSES.get(story_kind, "idle")


def pose_for_story(story, kind: str = "cover") -> str | None:
    """The pose a real story earns, taking its agreement state into account."""
    if getattr(story, "sensitive", False):
        return None
    state = _receipt.state(story)
    if state in ("disputed", "single"):
        return "puzzled"
    return pose_for(kind)


def draw_pip(canvas: Image.Image, pose: str = "idle", *, x: int = 0, y: int = 0,
             scale: int = 14) -> tuple[int, int]:
    """Stamp Pip. Returns his rendered size so callers can lay out around him.

    An unknown pose falls back to idle rather than raising: a missing sprite
    must never be an empty slot in a published frame.
    """
    grid = _pip.SPRITES.get(pose) or _pip.SPRITES["idle"]
    sprite = _pip.render(grid, scale)
    canvas.alpha_composite(sprite.convert("RGBA"), (x, y))
    return sprite.size


def pip_frame(cycle: list[str], t: float, fps_cycle: float = 7.0) -> str:
    """The frame of an animation cycle showing at time `t`."""
    if not cycle:
        return _pip.SPRITES["idle"]
    rate = fps_cycle if len(cycle) > 2 else fps_cycle * 0.43
    return cycle[int(t * rate) % len(cycle)]


CYCLES = {
    "walk": _pip.walk_cycle, "talk": _pip.talk_cycle, "jump": _pip.jump_cycle,
    "point": _pip.point_cycle, "present": _pip.present_cycle,
    "idle": _pip.idle_cycle,
}


# --------------------------------------------------------------------------- #
# Speech bubble
# --------------------------------------------------------------------------- #
def draw_bubble(canvas: Image.Image, draw: ImageDraw.ImageDraw, text: str, *,
                x: int, y: int, max_w: int, tail: str = "left",
                size: int = 34) -> tuple[int, int, int, int]:
    """A comic bubble with a chunky border and a stepped pixel tail.

    The tail is one polygon rather than three floating dashes so it stays in the
    pixel language of the sprite and reads as a shape.

    Returns the bounding box including the tail, so callers can assert it does
    not collide with anything.
    """
    font = fonts.label_font(size, 650)
    lines = fonts.wrap_text(font, text, max_w - 44)
    text_w = max(fonts.text_width(font, line) for line in lines)
    lh = int(size * 1.34)
    w = int(text_w) + 44
    h = len(lines) * lh + 34

    fill = hex_to_rgb(SURFACE_RAISED)
    ink = hex_to_rgb(INK)
    draw.rectangle([x, y, x + w, y + h], fill=fill)
    for off in (0, 3):                                  # chunky pixel border
        draw.rectangle([x - off, y - off, x + w + off, y + h + off],
                       outline=ink, width=3)
    ty = y + 17
    for line in lines:
        draw.text((x + 22, ty), line, font=font, fill=ink)
        ty += lh

    s, bottom = 11, y + h
    if tail == "right":
        tx = x + w - 30 - 3 * s
        pts = [(tx, bottom), (tx + 3 * s, bottom), (tx + 3 * s, bottom + 3 * s),
               (tx + 2 * s, bottom + 3 * s), (tx + 2 * s, bottom + 2 * s),
               (tx + s, bottom + 2 * s), (tx + s, bottom + s), (tx, bottom + s)]
    else:
        tx = x + 26
        pts = [(tx, bottom), (tx + 3 * s, bottom)]
        for i in range(3):                   # descending staircase on one side
            pts += [(tx + (3 - i) * s, bottom + (i + 1) * s),
                    (tx + (2 - i) * s, bottom + (i + 1) * s)]
    draw.polygon(pts, fill=fill)
    draw.line(pts[1:] + [pts[0]], fill=ink, width=3, joint="curve")
    draw.rectangle([tx + 2, bottom - 3, tx + 3 * s - 2, bottom + 2], fill=fill)
    return (x - 3, y - 3, x + w + 3, bottom + 3 * s)


def bubble_beside(canvas: Image.Image, draw: ImageDraw.ImageDraw, text: str, *,
                  pip_x: int, pip_w: int, pip_top: int, width: int,
                  margin: int | None = None, size: int = 34,
                  max_w: int = 520) -> tuple[int, int, int, int]:
    """Place a bubble on whichever side of Pip has room for it.

    Pip walks the full width of a reel, so a bubble pinned to his right runs off
    the frame by the time he reaches the sign-off. This measures the room on
    each side, sits on the one that has it, clamps to the margins and mirrors
    the tail so it still points at him.
    """
    m = MARGIN if margin is None else margin
    font = fonts.label_font(size, 650)
    lines = fonts.wrap_text(font, text, max_w - 44)
    text_w = max(fonts.text_width(font, line) for line in lines)
    w = int(text_w) + 44
    gap = 14

    room_right = (width - m) - (pip_x + pip_w + gap)
    room_left = (pip_x - gap) - m
    on_left = room_right < w and room_left >= w

    x = pip_x - gap - w if on_left else pip_x + pip_w + gap
    x = max(m, min(x, width - m - w))
    h = len(lines) * int(size * 1.34) + 34
    y = pip_top - h - 26
    return draw_bubble(canvas, draw, text, x=x, y=y, max_w=max_w,
                       tail="right" if on_left else "left", size=size)


# --------------------------------------------------------------------------- #
# Kinetic type
# --------------------------------------------------------------------------- #
_EMPHASIS = re.compile(r"(\*[^*]+\*)")


def tokenize(text: str) -> list[tuple[str, bool]]:
    """Split copy into (word, emphasised) pairs on `*asterisk*` spans.

    Trailing punctuation is pulled back onto the preceding word so a comma never
    starts a line on its own.
    """
    out: list[list] = []
    for part in _EMPHASIS.split(text):
        if not part:
            continue
        hero = part.startswith("*") and part.endswith("*") and len(part) > 2
        body = part[1:-1] if hero else part
        if not hero and out:
            match = re.match(r"^([,.;:!?)\]]+)", body)
            if match:
                out[-1][0] += match.group(1)
                body = body[match.end():]
        for word in body.split():
            out.append([word, hero])
    return [(w, h) for w, h in out]


def draw_rich(draw: ImageDraw.ImageDraw, text: str, *, x: int, y: int,
              max_w: int, size: int, tone, reveal: float = 1.0,
              base_weight: int = 450, hero_weight: int = 800,
              base_fill=None) -> int:
    """Wrapped copy where `*marked*` words carry the accent and extra weight.

    This is what the variable weight axis bought. Anton had one weight, so every
    word in a headline shouted at the same volume and nothing could be stressed
    without changing its size and reflowing the line.

    `reveal` draws only the first fraction of the words, which is how the reel
    reveals a line word by word without re-wrapping it as it goes: the layout is
    computed for the whole line and only the drawing is withheld.
    """
    tokens = tokenize(text)
    if not tokens:
        return y
    shown = len(tokens) if reveal >= 1 else max(1, int(len(tokens) * reveal + 0.999))
    base_fill = hex_to_rgb(TEXT_PRIMARY) if base_fill is None else base_fill
    hero_fill = safe_fill(tone, size)

    space = draw.textlength(" ", font=fonts.label_font(size, base_weight))
    lines: list[list] = []
    current: list = []
    current_w = 0.0
    for index, (word, hero) in enumerate(tokens):
        font = fonts.label_font(int(size * 1.08), hero_weight) if hero \
            else fonts.label_font(size, base_weight)
        tw = draw.textlength(word, font=font)
        if current_w + tw > max_w and current:
            lines.append(current)
            current, current_w = [], 0.0
        current.append((word, hero, font, tw, index))
        current_w += tw + space
    if current:
        lines.append(current)

    lh = int(size * 1.16)
    for line in lines:
        cx = x
        for word, hero, font, tw, index in line:
            if index < shown:
                draw.text((cx, y), word, font=font,
                          fill=hero_fill if hero else base_fill)
            cx += tw + space
        y += lh
    return y


# --------------------------------------------------------------------------- #
# The source strip
# --------------------------------------------------------------------------- #
def draw_receipt(canvas: Image.Image, draw: ImageDraw.ImageDraw, story, *,
                 x: int, y: int, tick_w: int = 13, tick_h: int = 46,
                 gap: int = 9, label: bool = True, names: bool = True,
                 short: bool = False, label_size: int = 34,
                 name_size: int = 28, dark: bool = False) -> int:
    """The source strip. Returns the y below everything it drew.

    Filled ticks are outlets that agree on the story's central claim. Hollow
    ticks are outlets that reported a different figure. Outlets that covered the
    story without mentioning the figure draw nothing at all, because a hollow
    tick reads as dissent and they did not dissent.

    A single-source story gets one outlined tick and says so. We do not publish
    those, but the strip renders honestly if one ever reaches it: a bar that is
    never thin is a bar that means nothing.
    """
    filled, hollow = _receipt.ticks(story)
    agree = hex_to_rgb(TONE_AGREE)
    muted = hex_to_rgb(TEXT_MUTED)
    for i in range(filled):
        bx = x + i * (tick_w + gap)
        draw.rectangle([bx, y, bx + tick_w, y + tick_h], fill=agree)
    for i in range(hollow):
        bx = x + (filled + i) * (tick_w + gap)
        draw.rectangle([bx, y, bx + tick_w, y + tick_h], outline=muted, width=3)

    below = y + tick_h
    ink = hex_to_rgb(CREAM if dark else TEXT_PRIMARY)
    soft = (168, 154, 137) if dark else hex_to_rgb(TEXT_SECONDARY)
    if label:
        below += 28
        text = _receipt.short_label(story) if short else _receipt.label(story)
        draw.text((x, below), text, font=fonts.label_font(label_size, 700),
                  fill=ink)
        below += int(label_size * 1.3)
    if names:
        line = _receipt.named(story, limit=3 if short else 4)
        if line:
            draw.text((x, below), line, font=fonts.label_font(name_size, 500),
                      fill=soft)
            below += int(name_size * 1.35)
    return below


def draw_receipt_inline(draw: ImageDraw.ImageDraw, story, *, x: int, y: int,
                        tick_w: int = 11, tick_h: int = 36, gap: int = 9,
                        dark: bool = False) -> int:
    """The reel's tighter strip: ticks and label on one line."""
    filled, hollow = _receipt.ticks(story)
    agree = hex_to_rgb(TONE_AGREE)
    muted = hex_to_rgb(TEXT_MUTED)
    cx = x
    for _ in range(filled):
        draw.rectangle([cx, y, cx + tick_w, y + tick_h], fill=agree)
        cx += tick_w + gap
    for _ in range(hollow):
        draw.rectangle([cx, y, cx + tick_w, y + tick_h], outline=muted, width=3)
        cx += tick_w + gap
    draw.text((cx + 24, y + 2), _receipt.short_label(story),
              font=fonts.label_font(26, 700),
              fill=hex_to_rgb(CREAM if dark else TEXT_PRIMARY))
    return y + tick_h
