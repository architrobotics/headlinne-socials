"""The carousel design system.

One place for the palette, the brand furniture and the reusable drawing
primitives that make every slide read as the same designed template: the top
brand bar, the category pill, the accent rule, the page-progress dots and the
premium fallback background used when a story has no usable photo.

Keeping these here (rather than inline in the slide renderers) is what lets the
cover, story and CTA layouts stay visually consistent, and makes the whole look
tunable from a single file alongside ``config``.
"""

from __future__ import annotations

import hashlib
import math
from functools import lru_cache
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter

from ..config import (BRAND_TERRACOTTA, BRAND_TERRACOTTA_HI, CATEGORY_COLORS,
                      CATEGORY_PILL, INK, INK_SOFT, LOGO_PATH, TEXT_MUTED,
                      TEXT_PRIMARY, TEXT_SECONDARY)
from . import fonts

# --------------------------------------------------------------------------- #
# Layout constants (canvas is 1080 x 1350)
# --------------------------------------------------------------------------- #
MARGIN = 76                 # left / right safe margin
TOP_BAR_Y = 70              # baseline band for the wordmark + pill
BOTTOM_BAR_Y = 1256         # baseline band for progress + handle

RGBA = tuple


# --------------------------------------------------------------------------- #
# Colour helpers
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
    return (
        int(ar + (br - ar) * t),
        int(ag + (bg - ag) * t),
        int(ab + (bb - ab) * t),
    )


def accent_for(category: str) -> tuple[int, int, int]:
    return hex_to_rgb(CATEGORY_COLORS.get(category, BRAND_TERRACOTTA))


def pill_label(category: str) -> str:
    return CATEGORY_PILL.get(category, category.upper())


# --------------------------------------------------------------------------- #
# Logo mark
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=16)
def logo_mark(size: int) -> Optional[Image.Image]:
    """The terracotta app tile, resized to `size`x`size` (cached). None if absent."""
    try:
        if LOGO_PATH.exists():
            return Image.open(LOGO_PATH).convert("RGBA").resize((size, size), Image.LANCZOS)
    except Exception:  # pragma: no cover - asset best-effort
        pass
    return None


# --------------------------------------------------------------------------- #
# Gradient / scrim builders
# --------------------------------------------------------------------------- #
def _alpha_ramp(h: int, stops: list[tuple[float, int]]) -> Image.Image:
    """Build a 1-px-wide vertical alpha ramp from (position, alpha) stops."""
    stops = sorted(stops)
    col = Image.new("L", (1, h), 0)
    px = col.load()
    for y in range(h):
        t = y / max(1, h - 1)
        # find surrounding stops
        prev = stops[0]
        nxt = stops[-1]
        for i in range(len(stops) - 1):
            if stops[i][0] <= t <= stops[i + 1][0]:
                prev, nxt = stops[i], stops[i + 1]
                break
        span = (nxt[0] - prev[0]) or 1.0
        local = (t - prev[0]) / span
        px[0, y] = int(prev[1] + (nxt[1] - prev[1]) * local)
    return col


def cinematic_scrim(w: int, h: int, tint=INK) -> Image.Image:
    """A full-height scrim for photo slides: a firm dark base rising from the
    bottom, a soft darken at the very top (for the brand bar) and a gentle
    overall tint. Keeps white type legible over any photo without hiding it."""
    tint_rgb = hex_to_rgb(tint) if isinstance(tint, str) else tint[:3]
    overlay = Image.new("RGBA", (w, h), rgba(tint_rgb, 0))

    # Bottom-up darkening (the main legibility band). Starts a little higher and
    # firmer so accent-coloured labels in the mid-band stay legible over bright
    # photos, while the upper half of the image still reads clearly.
    bottom = _alpha_ramp(h, [(0.0, 0), (0.30, 0), (0.48, 92), (0.64, 176),
                             (0.82, 230), (1.0, 252)])
    layer = Image.new("RGBA", (w, h), rgba(tint_rgb, 255))
    layer.putalpha(bottom.resize((w, h)))
    overlay = Image.alpha_composite(overlay, layer)

    # Top darkening so the wordmark / pill always sit on a readable band.
    top = _alpha_ramp(h, [(0.0, 170), (0.14, 60), (0.24, 0), (1.0, 0)])
    layer2 = Image.new("RGBA", (w, h), rgba(tint_rgb, 255))
    layer2.putalpha(top.resize((w, h)))
    overlay = Image.alpha_composite(overlay, layer2)

    # A whisper of overall tint to unify colour temperature across photos.
    overlay = Image.alpha_composite(overlay, Image.new("RGBA", (w, h), rgba(tint_rgb, 40)))
    return overlay


def panel_gradient(w: int, h: int, base=INK) -> Image.Image:
    """A subtle top-to-bottom gradient panel (for the CTA and fallbacks)."""
    top = scale(hex_to_rgb(base) if isinstance(base, str) else base, 1.35)
    bottom = hex_to_rgb(base) if isinstance(base, str) else base
    grad = Image.new("RGB", (1, h))
    px = grad.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = mix(top, bottom, t)
    return grad.resize((w, h)).convert("RGBA")


# --------------------------------------------------------------------------- #
# Premium fallback background (no usable photo)
# --------------------------------------------------------------------------- #
def brand_fallback(w: int, h: int, category: str, seed: str) -> Image.Image:
    """A designed fallback for slides with no photo.

    A warm, category-tinted radial wash on the ink base, a large ghosted brand
    mark bleeding off one corner, and a faint diagonal sheen. Deterministic per
    `seed` so consecutive fallbacks differ but a given slide is stable.
    """
    accent = accent_for(category)
    ink = hex_to_rgb(INK)
    ink_soft = hex_to_rgb(INK_SOFT)

    # Base vertical gradient (soft at top -> deep ink at the bottom).
    canvas = panel_gradient(w, h, INK)

    # Deterministic jitter so the glow sits in a slightly different place daily.
    digest = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    gx = 0.24 + ((digest % 53) / 53.0) * 0.52
    gy = 0.16 + (((digest >> 8) % 47) / 47.0) * 0.30

    # Radial accent glow, painted as an alpha-masked wash.
    glow_rgb = mix(ink_soft, accent, 0.55)
    cx, cy = int(w * gx), int(h * gy)
    radius = int(w * 0.95)
    mask = Image.new("L", (w, h), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=110)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=140))
    wash = Image.new("RGBA", (w, h), rgba(glow_rgb, 255))
    wash.putalpha(mask)
    canvas = Image.alpha_composite(canvas, wash)

    # Large ghost logo mark bleeding off the lower-right, very low opacity.
    mark = logo_mark(int(w * 0.9))
    if mark is not None:
        ghost = mark.copy()
        alpha = ghost.split()[3].point(lambda a: int(a * 0.06))
        ghost.putalpha(alpha)
        canvas.alpha_composite(ghost, (int(w * 0.42), int(h * 0.40)))

    # Faint diagonal sheen for a bit of life.
    sheen = Image.new("L", (w, h), 0)
    sdraw = ImageDraw.Draw(sheen)
    sdraw.polygon([(int(w * 0.0), h), (int(w * 0.55), 0),
                   (int(w * 0.72), 0), (int(w * 0.17), h)], fill=14)
    sheen = sheen.filter(ImageFilter.GaussianBlur(60))
    sheen_layer = Image.new("RGBA", (w, h), rgba((255, 255, 255), 255))
    sheen_layer.putalpha(sheen)
    canvas = Image.alpha_composite(canvas, sheen_layer)

    # Settle the bottom so type has a firm anchor.
    bottom = _alpha_ramp(h, [(0.0, 0), (0.55, 0), (1.0, 150)])
    blayer = Image.new("RGBA", (w, h), rgba(ink, 255))
    blayer.putalpha(bottom.resize((w, h)))
    canvas = Image.alpha_composite(canvas, blayer)
    return canvas


# --------------------------------------------------------------------------- #
# Furniture primitives
# --------------------------------------------------------------------------- #
def draw_top_bar(canvas: Image.Image, draw: ImageDraw.ImageDraw, category: str,
                 *, show_pill: bool = True) -> None:
    """The brand bar every photo slide carries: the logo mark + HEADLINNE
    wordmark on the left, and the category pill on the right."""
    y = TOP_BAR_Y
    mark_size = 46
    mark = logo_mark(mark_size)
    x = MARGIN
    if mark is not None:
        canvas.alpha_composite(mark, (x, y - 2))
        x += mark_size + 18

    word_font = fonts.label_font(30, weight=800)
    # Vertically centre the wordmark against the mark.
    wf_h = fonts.line_height(word_font)
    wy = y - 2 + (mark_size - wf_h) // 2 - 2
    fonts.draw_tracked(draw, (x, wy), "HEADLINNE", word_font,
                       fill=rgba(TEXT_PRIMARY), tracking=3.2)

    if show_pill:
        draw_pill_right(draw, pill_label(category), accent_for(category),
                        y_center=y - 2 + mark_size // 2)


def draw_pill_right(draw: ImageDraw.ImageDraw, text: str, accent,
                    *, y_center: int) -> None:
    """A small solid accent pill flush to the right margin, vertically centred
    on `y_center`."""
    from ..config import SLIDE_W

    font = fonts.label_font(23, weight=800)
    tracking = 1.8
    tw = fonts.tracked_width(font, text, tracking)
    pad_x, pad_y = 22, 12
    fh = fonts.line_height(font)
    w = tw + pad_x * 2
    h = fh + pad_y * 2
    x1 = SLIDE_W - MARGIN
    x0 = x1 - w
    y0 = y_center - h // 2
    y1 = y0 + h
    draw.rounded_rectangle([x0, y0, x1, y1], radius=h // 2, fill=rgba(accent))
    # Dark text on the bright pill for punch and legibility.
    ty = y0 + pad_y - font.getbbox(text)[1]
    fonts.draw_tracked(draw, (x0 + pad_x, ty), text, font,
                       fill=rgba(INK), tracking=tracking)


def draw_tracked_shadowed(canvas: Image.Image, xy, text: str, font, fill,
                          *, tracking: float = 0.0, shadow_alpha: int = 130) -> int:
    """Tracked (letter-spaced) text with a soft drop shadow, for accent-coloured
    labels that must stay legible over bright photography."""
    x, y = xy
    if shadow_alpha:
        shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(shadow)
        fonts.draw_tracked(sdraw, (x, y), text, font, fill=(0, 0, 0, shadow_alpha),
                           tracking=tracking)
        shadow = shadow.filter(ImageFilter.GaussianBlur(5))
        canvas.alpha_composite(shadow)
    draw = ImageDraw.Draw(canvas)
    return fonts.draw_tracked(draw, (x, y), text, font, fill=fill, tracking=tracking)


def draw_accent_rule(draw: ImageDraw.ImageDraw, x: int, y: int, accent,
                     *, width: int = 92, thickness: int = 7) -> None:
    draw.rounded_rectangle([x, y, x + width, y + thickness],
                           radius=thickness // 2, fill=rgba(accent))


def draw_progress(canvas: Image.Image, draw: ImageDraw.ImageDraw, *,
                  total: int, active: int, accent) -> None:
    """A row of page-progress pips centred at the bottom-left margin. The active
    pip is an accent-coloured lozenge; the rest are dim dots."""
    y = BOTTOM_BAR_Y + 6
    x = MARGIN
    dot = 9
    gap = 12
    long = 30  # the active pip stretches into a lozenge
    for i in range(total):
        if i == active:
            draw.rounded_rectangle([x, y, x + long, y + dot], radius=dot // 2,
                                   fill=rgba(accent))
            x += long + gap
        else:
            draw.ellipse([x, y, x + dot, y + dot], fill=rgba(TEXT_MUTED, 150))
            x += dot + gap


def draw_handle(draw: ImageDraw.ImageDraw, text: str, *, accent=None) -> None:
    """The @handle / website, flush right on the bottom bar."""
    from ..config import SLIDE_W

    font = fonts.label_font(24, weight=700)
    tracking = 1.2
    tw = fonts.tracked_width(font, text, tracking)
    x = SLIDE_W - MARGIN - tw
    y = BOTTOM_BAR_Y - 2
    fonts.draw_tracked(draw, (x, y), text, font,
                       fill=rgba(accent or TEXT_SECONDARY), tracking=tracking)


def draw_swipe_hint(draw: ImageDraw.ImageDraw, accent, *, y: int) -> None:
    """A 'SWIPE' pill with an arrow, flush right, used on the cover."""
    from ..config import SLIDE_W

    label = "SWIPE"
    font = fonts.label_font(22, weight=800)
    tracking = 2.0
    tw = fonts.tracked_width(font, label, tracking)
    arrow_w = 26
    pad_x, pad_y = 24, 13
    fh = fonts.line_height(font)
    inner = tw + 14 + arrow_w
    w = inner + pad_x * 2
    h = fh + pad_y * 2
    x1 = SLIDE_W - MARGIN
    x0 = x1 - w
    y0 = y
    draw.rounded_rectangle([x0, y0, x1, y0 + h], radius=h // 2,
                           outline=rgba(accent), width=3)
    tx = x0 + pad_x
    ty = y0 + pad_y - font.getbbox(label)[1]
    fonts.draw_tracked(draw, (tx, ty), label, font, fill=rgba(accent), tracking=tracking)
    # Arrow.
    ax = tx + tw + 16
    ay = y0 + h // 2
    draw.line([(ax, ay), (ax + arrow_w, ay)], fill=rgba(accent), width=4)
    draw.line([(ax + arrow_w - 11, ay - 9), (ax + arrow_w, ay)], fill=rgba(accent), width=4)
    draw.line([(ax + arrow_w - 11, ay + 9), (ax + arrow_w, ay)], fill=rgba(accent), width=4)


def draw_source_line(draw: ImageDraw.ImageDraw, sources: str, accent,
                     *, x: int, y: int) -> int:
    """Draw the trust line: an accent diamond + 'SOURCES  <names>'. Returns the
    y below the line. Skipped cleanly when there are no sources."""
    if not sources:
        return y
    label_font = fonts.label_font(22, weight=800)
    name_font = fonts.label_font(24, weight=600)
    # Accent diamond bullet.
    d = 11
    cy = y + fonts.line_height(name_font) // 2
    draw.polygon([(x, cy - d), (x + d, cy), (x, cy + d), (x - d, cy)], fill=rgba(accent))
    tx = x + d + 16
    label = "SOURCES"
    fonts.draw_tracked(draw, (tx, y + 2), label, label_font,
                       fill=rgba(accent), tracking=1.6)
    tx += fonts.tracked_width(label_font, label, 1.6) + 16
    draw.text((tx, y), sources, font=name_font, fill=rgba(TEXT_SECONDARY))
    return y + fonts.line_height(name_font)
