"""The cut-paper furniture laid over the set.

Each piece copies one job from the reference reels:

  title       a strip of crumpled cream paper, taped at both top corners,
              carrying the chapter in heavy capitals. It is the question the
              beat answers, read before the answer.
  stat card   a paper card with the Headlinne tile as a speech-bubble badge,
              one figure that counts up, and a small caption under it.
  chips       the spoken words, one to three at a time, each torn out of
              terracotta paper in a bold serif, tilted a little, popping in as
              they are said.
  lower third a strip of blue paper from the left edge with condensed white
              capitals, quoting a TV chyron, for the one hard fact of a beat.
  stamp       a rubber stamp that slams onto the frame: one word, a verdict.
  comment box the closing prompt, a comment field being typed into.

Pieces are built once and cached by their content; per-frame motion is a
transform of a cached image, never a redraw, so the frame budget goes on the
set and Pip.
"""

from __future__ import annotations

import math
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

from ...config import LOGO_PATH
from .. import fonts
from . import paper
from .paper import Rng, shade

CREAM_PAPER = (243, 236, 222)
INK = (24, 18, 14)
CHIP_FILL = (214, 108, 70)        # the reference chip terracotta, a step lighter
CHIP_TEXT = (253, 243, 228)       #   than the brand tone so cream type pops
CHYRON = (30, 84, 166)
CHYRON_DEEP = (20, 56, 120)
TAPE = (214, 196, 150)

TITLE_SIZE = 58
TITLE_MIN = 32
CHIP_SIZE = 66
CHIP_GAP = 12


# --------------------------------------------------------------------------- #
# Title strip
# --------------------------------------------------------------------------- #
def _crumple(img: Image.Image, key) -> Image.Image:
    """Creases: a few faint diagonal folds, light on one side, dark on the
    other, which is what separates crumpled paper from a flat label."""
    w, h = img.size
    rng = Rng("crumple", key)
    folds = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(folds)
    for _ in range(max(3, w // 160)):
        x = rng.uniform(0, w)
        dx = rng.uniform(-80, 80)
        d.line([(x, 0), (x + dx, h)], fill=(90, 70, 50, 34), width=3)
        d.line([(x + 4, 0), (x + dx + 4, h)], fill=(255, 255, 255, 46), width=3)
    folds = folds.filter(ImageFilter.GaussianBlur(1.2))
    out = img.copy()
    out.alpha_composite(folds)
    out.putalpha(img.getchannel("A"))
    return out


def tape_piece(w: int = 92, h: int = 40, *, key="", angle: float = 0) -> Image.Image:
    """A torn scrap of masking tape, translucent."""
    m = paper.torn_mask(w, h, key=("tape", key), jag=5, edges="lr", step=7)
    piece = paper.cut(m, TAPE, key=("tapetex", key), mottle=0.4)
    piece.putalpha(m.point(lambda a: int(a * 0.86)))
    return paper.rotated(piece, angle)


@lru_cache(maxsize=32)
def title(text: str, max_w: int = 960) -> Image.Image:
    """The chapter title on a taped paper strip, ready to lay on the frame."""
    text = " ".join(text.upper().split())
    pad_x, pad_y = 34, 20
    size = TITLE_SIZE
    font = fonts.label_font(size, 800)
    while size > TITLE_MIN and fonts.text_width(font, text) + 2 * pad_x > max_w:
        size -= 2
        font = fonts.label_font(size, 800)
    tw = fonts.text_width(font, text)
    asc, desc = font.getmetrics()
    w = max(int(max_w * 0.62), tw + 2 * pad_x)
    w = min(w, max_w)
    h = asc + 2 * pad_y
    m = paper.torn_mask(w, h, key=("title", text), jag=4, edges="tb", step=18)
    strip = _crumple(paper.cut(m, CREAM_PAPER, key=("titlepaper", text)), text)
    ImageDraw.Draw(strip).text((w / 2, h / 2 + 2), text, font=font, fill=INK,
                               anchor="mm")
    out = Image.new("RGBA", (w + 80, h + 70), (0, 0, 0, 0))
    out.alpha_composite(paper.shadowed(strip, offset=(4, 8), blur=8, strength=0.5),
                        (40 - paper.pad_for((4, 8), 8), 34 - paper.pad_for((4, 8), 8)))
    out.alpha_composite(tape_piece(96, 40, key=(text, "l"), angle=32), (0, 0))
    out.alpha_composite(tape_piece(96, 40, key=(text, "r"), angle=-34),
                        (w + 80 - 120, 0))
    return paper.rotated(out, -0.6)


# --------------------------------------------------------------------------- #
# Stat card
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=4)
def _logo(size: int) -> Image.Image | None:
    try:
        return Image.open(LOGO_PATH).convert("RGBA").resize((size, size), Image.LANCZOS)
    except Exception:  # pragma: no cover - asset best-effort
        return None


@lru_cache(maxsize=4)
def badge(size: int = 104) -> Image.Image:
    """The Headlinne tile as a speech bubble: the card's 'who is talking'."""
    out = Image.new("RGBA", (size + 8, size + 28), (0, 0, 0, 0))
    tile = _logo(size)
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1],
                                        radius=size // 5, fill=255)
    if tile is None:
        tile = Image.new("RGBA", (size, size), (196, 86, 47, 255))
    tile = tile.copy()
    tile.putalpha(m)
    tail = paper.mask_of(size, size + 28, lambda d: d.polygon(
        [(size * 0.16, size - 4), (size * 0.42, size - 4), (size * 0.12, size + 26)],
        fill=255))
    tail_img = Image.new("RGBA", tail.size, (196, 86, 47, 0))
    tail_img.putalpha(tail)
    out.alpha_composite(tail_img, (0, 0))
    out.alpha_composite(tile, (0, 0))
    return out


@lru_cache(maxsize=16)
def stat_base(label: str, number_w: int) -> Image.Image:
    """The card without its figure. The figure is drawn per frame as it counts."""
    label = label.upper()
    lf = fonts.label_font(24, 700)
    bw = badge().width
    w = 36 + bw + 22 + max(number_w, fonts.text_width(lf, label)) + 40
    h = 150
    m = paper.torn_mask(w, h, key=("stat", label), jag=3, edges="tblr", step=22)
    card = _crumple(paper.cut(m, CREAM_PAPER, key=("statpaper", label)), label)
    card.alpha_composite(badge(), (26, 18))
    ImageDraw.Draw(card).text((36 + bw + 22, 104), label, font=lf, fill=(120, 108, 96))
    return card


def stat_card(value: str, label: str, *, progress: float = 1.0) -> Image.Image:
    """The stat card with `value` counted up to `progress` of the way."""
    from ..graphics import animate_number

    return _stat_card(value, label, animate_number(value, progress))


@lru_cache(maxsize=256)
def _stat_card(value: str, label: str, shown: str) -> Image.Image:
    nf = fonts.label_font(78, 800)
    final_w = fonts.text_width(nf, value)
    card = stat_base(label, final_w).copy()
    ImageDraw.Draw(card).text((36 + badge().width + 22, 14), shown, font=nf, fill=INK)
    return paper.rotated(paper.shadowed(card, offset=(5, 10), blur=10, strength=0.5),
                         -1.2)


# --------------------------------------------------------------------------- #
# Word chips
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=512)
def chip(word: str, seed: int = 0, size: int = CHIP_SIZE) -> Image.Image:
    """One spoken word on a scrap of torn terracotta paper.

    The quad is jittered at each corner rather than drawn square, which is
    what makes it read as torn paper rather than a rounded button.
    """
    font = fonts.chip_font(size)
    bbox = font.getbbox(word)
    tw = bbox[2] - bbox[0]
    asc, desc = font.getmetrics()
    pad_x, pad_y = 18, 12
    w, h = tw + 2 * pad_x, asc + desc // 2 + 2 * pad_y - 8
    rng = Rng("chip", word, seed)
    j = 5
    quad = [(rng.uniform(0, j), rng.uniform(0, j)),
            (w - rng.uniform(0, j), rng.uniform(0, j)),
            (w - rng.uniform(0, j), h - rng.uniform(0, j)),
            (rng.uniform(0, j), h - rng.uniform(0, j))]
    m = paper.mask_of(w, h, lambda d: d.polygon(quad, fill=255))
    piece = paper.cut(m, CHIP_FILL, key=("chippaper", word, seed), mottle=0.8)
    d = ImageDraw.Draw(piece)
    # A darker torn lip along the bottom, the edge of the sheet it came from.
    d.line([quad[3], quad[2]], fill=shade(CHIP_FILL, 0.78), width=4)
    d.text((w / 2, h / 2 + 1), word, font=font, fill=CHIP_TEXT, anchor="mm")
    angle = rng.uniform(-3.2, 3.2)
    return paper.rotated(paper.shadowed(piece, offset=(3, 6), blur=5, strength=0.45),
                         angle)


def chip_offsets(words: list[str], seed: int) -> list[int]:
    """Each chip sits a few pixels off the line, like paper slapped down by hand."""
    rng = Rng("chipline", seed, *words)
    return [int(rng.uniform(-8, 8)) for _ in words]


def chip_row_width(words: list[str], seed: int = 0, size: int = CHIP_SIZE) -> int:
    imgs = [chip(w, seed + i, size) for i, w in enumerate(words)]
    pad = paper.pad_for((3, 6), 5)
    return sum(im.width - 2 * pad for im in imgs) + CHIP_GAP * (len(imgs) - 1)


def pop_scale(age: float) -> float:
    """Pop-in: 0.6 to a small overshoot and back to 1 in about a sixth of a second."""
    if age <= 0:
        return 0.0
    if age >= 0.18:
        return 1.0
    t = age / 0.18
    return 0.6 + 0.4 * (1 - (1 - t) ** 3) + 0.10 * math.sin(math.pi * t)


# --------------------------------------------------------------------------- #
# Lower third
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=16)
def lower_third(text: str, max_w: int = 760) -> Image.Image:
    """The chyron: blue torn paper from the frame edge, condensed white caps."""
    text = " ".join(text.upper().split())
    size = 56
    font = fonts.chyron_font(size)
    lines = fonts.wrap_text(font, text, max_w - 80)
    while len(lines) > 2 and size > 40:
        size -= 4
        font = fonts.chyron_font(size)
        lines = fonts.wrap_text(font, text, max_w - 80)
    lines = lines[:2]
    lh = int(size * 1.12)
    w = min(max_w, max(fonts.text_width(font, ln) for ln in lines) + 110)
    h = lh * len(lines) + 46
    m = paper.torn_mask(w, h, key=("chyron", text), jag=9, edges="tr", step=16)
    strip = paper.cut(m, CHYRON, key=("chyronpaper", text), mottle=0.9)
    grad = paper.gradient(w, h, CHYRON, CHYRON_DEEP)
    grad.putalpha(m.point(lambda a: int(a * 0.55)))
    strip.alpha_composite(grad)
    d = ImageDraw.Draw(strip)
    for i, line in enumerate(lines):
        d.text((48, 26 + i * lh), line, font=font, fill=(250, 250, 252))
    return paper.shadowed(strip, offset=(4, 10), blur=10, strength=0.5)


# --------------------------------------------------------------------------- #
# Stamp
# --------------------------------------------------------------------------- #
STAMP_TONES = {
    "good": (36, 132, 86),
    "bad": (206, 52, 40),
    "neutral": (40, 64, 140),
}


@lru_cache(maxsize=16)
def stamp(text: str, tone: str = "neutral") -> Image.Image:
    """A rubber stamp: a bordered word with ink that did not take everywhere."""
    text = text.upper()
    col = STAMP_TONES.get(tone, STAMP_TONES["neutral"])
    font = fonts.chyron_font(110)
    tw = fonts.text_width(font, text)
    w, h = tw + 110, 190
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, w - 9, h - 9], radius=22, outline=(*col, 255), width=12)
    d.rounded_rectangle([26, 26, w - 27, h - 27], radius=14, outline=(*col, 255), width=4)
    d.text((w / 2, h / 2 + 4), text, font=font, fill=(*col, 255), anchor="mm")
    # Ink dropout: knock holes in the alpha so it reads as stamped, not printed.
    noise = Image.effect_noise((w, h), 90).point(lambda v: 0 if v > 168 else 255)
    alpha = Image.composite(img.getchannel("A"), Image.new("L", (w, h), 0), noise)
    img.putalpha(alpha.point(lambda a: int(a * 0.92)))
    return paper.rotated(img, -9)


def slam_scale(age: float) -> float:
    """The stamp arrives big and lands in a tenth of a second."""
    if age <= 0:
        return 0.0
    if age >= 0.14:
        return 1.0
    t = age / 0.14
    return 1.9 - 0.9 * (t ** 2)


# --------------------------------------------------------------------------- #
# Comment box
# --------------------------------------------------------------------------- #
def comment_box(text: str, typed: float, *, width: int = 900) -> Image.Image:
    """The closing prompt: a comment field with `typed` of `text` entered."""
    typed = max(0.0, min(1.0, typed))
    count = int(round(len(text) * typed))
    state = 2 if typed >= 1 else (1 if typed > 0 else 0)
    return _comment_box(text, count, state, width)


@lru_cache(maxsize=1)
def _avatar() -> Image.Image:
    """Pip, happy, as the commenter's profile picture."""
    from .. import pip as _pip
    from . import voxel

    return voxel.render(_pip.SPRITES["happy"], 6)


@lru_cache(maxsize=128)
def _comment_box(text: str, count: int, state: int, width: int) -> Image.Image:
    typed = 1.0 if state == 2 else (0.5 if state == 1 else 0.0)
    avatar = _avatar()
    h = 124
    img = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, width - 1, h - 1], radius=h // 2,
                        fill=(252, 250, 246, 255), outline=(220, 214, 204, 255), width=3)
    av = 88
    if avatar is not None:
        a = avatar.copy()
        a.thumbnail((av, av), Image.LANCZOS)
        disc = Image.new("RGBA", (av, av), (196, 86, 47, 255))
        m = Image.new("L", (av, av), 0)
        ImageDraw.Draw(m).ellipse([0, 0, av - 1, av - 1], fill=255)
        disc.alpha_composite(a, ((av - a.width) // 2, (av - a.height) // 2 + 6))
        disc.putalpha(m)
        img.alpha_composite(disc, (18, (h - av) // 2))
    font = fonts.label_font(46, 800)
    shown = text[:count]
    d.text((126, h // 2), shown or "Add a comment...", font=font,
           fill=INK if shown else (150, 142, 132), anchor="lm")
    if 0 < typed < 1:
        cx = 126 + fonts.text_width(font, shown) + 6
        d.rectangle([cx, h // 2 - 26, cx + 4, h // 2 + 26], fill=(60, 120, 230))
    pf = fonts.label_font(34, 700)
    d.text((width - 40, h // 2), "Post", font=pf,
           fill=(60, 120, 230) if typed >= 1 else (170, 196, 240), anchor="rm")
    return paper.shadowed(img, offset=(0, 10), blur=14, strength=0.45)


# --------------------------------------------------------------------------- #
# Source tag
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=8)
def source_tag(text: str, max_w: int = 520) -> Image.Image:
    """A small paper tag naming who reported it. Headlinne's receipt, kept."""
    font = fonts.label_font(24, 700)
    label = text.upper()
    while fonts.text_width(font, label) > max_w - 44 and len(label) > 8:
        label = label.rsplit(" ", 1)[0].rstrip(" ·,") + "…"
    w = fonts.text_width(font, label) + 44
    h = 50
    m = paper.torn_mask(w, h, key=("srctag", text), jag=2, edges="lr", step=10)
    tag = paper.cut(m, (236, 228, 212), key=("srctagpaper", text))
    ImageDraw.Draw(tag).text((22, h / 2), label, font=font, fill=(84, 74, 64), anchor="lm")
    return paper.rotated(paper.shadowed(tag, offset=(3, 6), blur=6, strength=0.4), 1.0)
