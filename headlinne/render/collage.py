"""The collage layer: paper grain, tape labels, torn-paper chips, die-cut Pip.

Added in Oct 2026 when the founder asked for the reels to borrow the
cut-paper look that a lot of explainer accounts on Instagram now use: a scrap
of masking tape carrying the section title, the key words of the spoken line
torn out of coloured paper and slapped onto the frame, and the mascot cut out
like a sticker. Those are genre techniques, not one creator's frames, and every
colour and face here is still Headlinne's own - Manrope, the category tones,
Pip. What this file must never become is a copy of a specific account's
layouts with the topics swapped.

Everything is deterministic. A frame is rendered from `t` alone, so the jagged
edge of a chip is seeded from the word and its position rather than from a
random generator - otherwise every chip would re-tear itself thirty times a
second.

Every verb returns the box it drew, so the reel can trace it for the overlap
harness exactly as it traces everything else.
"""

from __future__ import annotations

import math
import zlib
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

from ..config import CREAM, INK, NIGHT, SURFACE
from . import fonts

# Masking tape: a warm, slightly translucent kraft that reads as tape on paper
# and as tape on the night ground. INK on it measures well above 4.5:1.
TAPE_FILL = (231, 214, 168)
TAPE_ALPHA = 236
TAPE_TILT = -1.2          # degrees; one consistent lean, so it reads as placed
# The most a strip's far end may rise above its near end, in pixels. The lean
# is capped by this rather than fixed in degrees: at a fixed angle a long label
# rose high enough to push the strip into the stage, which the overlap gate
# rightly treats as a reason not to publish the reel at all.
TAPE_MAX_RISE = 8

# How far a chip's paper reaches past the glyphs it carries.
CHIP_PAD_X = 12
CHIP_PAD_Y = 8
CHIP_TILTS = (-2.4, 1.8, -1.2, 2.6)

# Pip's sticker border. The renderer offsets him by this much so the border's
# outer edge sits where the bare sprite used to, and the margin check holds.
STICKER_BORDER = 9
STICKER_FILL = (255, 252, 245, 255)

TAPE_LABEL_SIZE = 24


def _rng(*parts) -> "_Seeded":
    return _Seeded(zlib.crc32("|".join(map(str, parts)).encode()))


class _Seeded:
    """A tiny LCG. random.Random would do, but this keeps the seed explicit."""

    def __init__(self, seed: int):
        self.state = seed or 1

    def uniform(self, lo: float, hi: float) -> float:
        self.state = (1103515245 * self.state + 12345) & 0x7FFFFFFF
        return lo + (hi - lo) * (self.state / 0x7FFFFFFF)


# --------------------------------------------------------------------------- #
# Ground
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=4)
def _ground(w: int, h: int, dark: bool) -> Image.Image:
    base = Image.new("RGBA", (w, h), (*_hex(NIGHT if dark else SURFACE), 255))
    # Two scales of noise: a slow mottle, which is what makes paper read as
    # paper at phone size, and a fine tooth on top of it. Both are faint - the
    # type has to sit on this, and the contrast floors are measured on the
    # flat colour.
    mottle = Image.effect_noise((max(1, w // 9), max(1, h // 9)), 60) \
        .resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(4))
    tooth = Image.effect_noise((w, h), 34)
    grain = Image.blend(mottle, tooth, 0.35)
    shade = grain.point(lambda v: int(max(0, 128 - v) * (0.16 if dark else 0.20)))
    light = grain.point(lambda v: int(max(0, v - 128) * (0.10 if dark else 0.22)))
    base.alpha_composite(_tinted((0, 0, 0) if dark else (60, 40, 20), shade))
    base.alpha_composite(_tinted((255, 250, 240), light))
    return base


def ground(w: int, h: int, *, dark: bool = False) -> Image.Image:
    """The paper ground with grain, built once and copied per frame."""
    return _ground(w, h, dark).copy()


def _tinted(rgb, alpha: Image.Image) -> Image.Image:
    layer = Image.new("RGBA", alpha.size, (*rgb, 0))
    layer.putalpha(alpha)
    return layer


# --------------------------------------------------------------------------- #
# Tape
# --------------------------------------------------------------------------- #
def _torn_end(rng: _Seeded, x: float, y0: float, y1: float, *,
              outward: int) -> list[tuple[float, float]]:
    """A zigzag edge from y0 to y1 at x; `outward` is -1 for left, 1 for right."""
    points, steps = [], 7
    for i in range(steps + 1):
        y = y0 + (y1 - y0) * i / steps
        jag = rng.uniform(2, 9) if i % 2 else rng.uniform(-2, 2)
        points.append((x + outward * jag, y))
    return points


def tape_label(text: str, *, size: int = TAPE_LABEL_SIZE,
               tilt: float = TAPE_TILT, max_w: int | None = None) -> Image.Image:
    """A strip of masking tape with `text` set on it in tracked small caps.

    A label too long for `max_w` steps its type down rather than running off
    the frame; chapter names come from the model and are not length-checked.
    """
    text = text.upper()
    pad_x, pad_y = 26, 12
    for step in range(size, 15, -2):
        font = fonts.label_font(step, 760)
        tracking = step * 0.08
        tw = fonts.tracked_width(font, text, tracking)
        if max_w is None or tw + 2 * pad_x + 24 <= max_w:
            break
    bbox = font.getbbox("HXg")
    th = bbox[3] - bbox[1]
    w, h = int(tw + 2 * pad_x), int(th + 2 * pad_y)
    limit = math.degrees(math.asin(min(1.0, TAPE_MAX_RISE / max(w, 1))))
    tilt = math.copysign(min(abs(tilt), limit), tilt)

    strip = Image.new("RGBA", (w + 24, h + 24), (0, 0, 0, 0))
    draw = ImageDraw.Draw(strip)
    rng = _rng("tape", text)
    left = _torn_end(rng, 12, 12, 12 + h, outward=-1)
    right = _torn_end(rng, 12 + w, 12 + h, 12, outward=1)
    draw.polygon(left + right, fill=(*TAPE_FILL, TAPE_ALPHA))
    # Two faint lengthwise fibres, which is what separates tape from a label.
    for fy in (0.3, 0.72):
        y = 12 + h * fy
        draw.line([(16, y), (8 + w, y + rng.uniform(-1, 1))],
                  fill=(255, 248, 226, 70), width=2)
    fonts.draw_tracked(draw, (12 + pad_x, 12 + pad_y - bbox[1]), text, font,
                       fill=_hex(INK), tracking=tracking)
    return _with_shadow(strip.rotate(tilt, resample=Image.BICUBIC, expand=True),
                        offset=(0, 3), blur=3, alpha=46)


def place(canvas: Image.Image, img: Image.Image, x: int, y: int
          ) -> tuple[int, int, int, int]:
    canvas.alpha_composite(img, (int(x), int(y)))
    bbox = img.getbbox() or (0, 0, img.width, img.height)
    return (int(x) + bbox[0], int(y) + bbox[1], int(x) + bbox[2], int(y) + bbox[3])


# --------------------------------------------------------------------------- #
# Torn-paper chips
# --------------------------------------------------------------------------- #
def chip_text_fill(fill) -> tuple[int, int, int]:
    """CREAM on the chip where it clears the large-text floor, else INK.

    Every category tone clears it today; the fallback exists so a new category
    colour can never ship cream-on-yellow without anyone deciding to.
    """
    from .theme import contrast_ratio

    return _hex(CREAM) if contrast_ratio(_hex(CREAM), fill) >= 3.0 else _hex(INK)


def chip(word: str, font, fill, *, seed, pop: float = 1.0
         ) -> tuple[Image.Image, tuple[float, float]]:
    """One word torn out of coloured paper.

    `pop` runs 0 -> 1 as the word arrives and drives a small overshoot in
    scale, the slap of a sticker going down. At 1.0 the chip is at rest.

    Returns the image and the point in it where the word's centre sits, so
    the caller can drop the chip onto the slot the layout reserved for it
    whatever the rotation and the shadow did to the image's size.
    """
    bbox = font.getbbox(word)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    w, h = tw + 2 * CHIP_PAD_X, th + 2 * CHIP_PAD_Y
    m = 8
    img = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    rng = _rng("chip", word, seed)

    # Torn on all four sides, with the long edges torn more gently than the
    # short ones - paper tears straighter along its length.
    pts: list[tuple[float, float]] = []
    across = max(4, w // 22)
    down = max(3, h // 14)
    for i in range(across + 1):
        pts.append((m + w * i / across, m + rng.uniform(-3, 3)))
    for i in range(1, down + 1):
        pts.append((m + w + rng.uniform(-5, 5), m + h * i / down))
    for i in range(across - 1, -1, -1):
        pts.append((m + w * i / across, m + h + rng.uniform(-3, 3)))
    for i in range(down - 1, 0, -1):
        pts.append((m + rng.uniform(-5, 5), m + h * i / down))
    draw.polygon(pts, fill=(*fill, 255))
    # The paper's white core showing at a torn edge: a thin lighter rim along
    # the bottom, offset so it only peeks out.
    rim = [(x, y + 2) for x, y in pts[across + down: 2 * across + down + 1]]
    if len(rim) > 1:
        draw.line(rim, fill=(255, 250, 240, 150), width=2)
    draw.text((m + CHIP_PAD_X - bbox[0], m + CHIP_PAD_Y - bbox[1]), word,
              font=font, fill=chip_text_fill(fill))

    tilt = CHIP_TILTS[int(rng.uniform(0, len(CHIP_TILTS) - 0.001))]
    scale = 1.0
    if pop < 1.0:
        p = max(0.0, pop)
        # ease_out_back from 0.55: lands a touch big, then settles.
        c1 = 1.9
        eased = 1 + (c1 + 1) * (p - 1) ** 3 + c1 * (p - 1) ** 2
        scale = 0.55 + 0.45 * eased
        tilt *= 1 + 2.5 * (1 - p)
    out = img.rotate(tilt, resample=Image.BICUBIC, expand=True)
    if abs(scale - 1.0) > 0.01:
        out = out.resize((max(1, int(out.width * scale)),
                          max(1, int(out.height * scale))), Image.BICUBIC)
    centre = (out.width / 2, out.height / 2)
    return _with_shadow(out, offset=(3, 5), blur=4, alpha=60), centre


def chip_extent(word: str, font) -> tuple[float, int]:
    """(advance, height) a chip claims in a line, for layout before drawing."""
    bbox = font.getbbox(word)
    return (bbox[2] - bbox[0]) + 2 * CHIP_PAD_X, (bbox[3] - bbox[1]) + 2 * CHIP_PAD_Y


# --------------------------------------------------------------------------- #
# Sticker
# --------------------------------------------------------------------------- #
def sticker(sprite: Image.Image, border: int = STICKER_BORDER) -> Image.Image:
    """Cut a sprite out like a die-cut sticker: an off-white border that follows
    its silhouette, and a soft shadow lifting it off the paper.

    The border is grown from the sprite's own alpha, so it follows Pip's wings
    and feet in every pose rather than being a rounded box around him.
    """
    pad = border + 8
    w, h = sprite.width + 2 * pad, sprite.height + 2 * pad
    alpha = Image.new("L", (w, h), 0)
    alpha.paste(sprite.getchannel("A"), (pad, pad))
    grown = alpha.filter(ImageFilter.MaxFilter(2 * border + 1))
    # Round the stepped corners the pixel grid leaves in the grown mask.
    grown = grown.filter(ImageFilter.GaussianBlur(2)).point(
        lambda v: 255 if v > 110 else 0)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.alpha_composite(_tinted(STICKER_FILL[:3], grown))
    out.alpha_composite(sprite, (pad, pad))
    return _with_shadow(out, offset=(4, 7), blur=6, alpha=70)


def _with_shadow(img: Image.Image, *, offset=(3, 5), blur: int = 4,
                 alpha: int = 60) -> Image.Image:
    """`img` over a soft shadow of itself. The canvas grows to hold the shadow
    on the offset side only, so the original's top-left stays at (0, 0)."""
    ox, oy = offset
    w, h = img.width + abs(ox) + 2 * blur, img.height + abs(oy) + 2 * blur
    shadow_alpha = img.getchannel("A").point(lambda v: v * alpha // 255)
    shadow = Image.new("L", (w, h), 0)
    shadow.paste(shadow_alpha, (max(0, ox), max(0, oy)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    out = _tinted((40, 28, 18), shadow)
    out.alpha_composite(img, (max(0, -ox), max(0, -oy)))
    return out


def _hex(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore

