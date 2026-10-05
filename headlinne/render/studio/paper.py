"""Cut-paper primitives the sets and overlays are built from.

Everything in a studio frame is a sheet of something - card, kraft, felt,
masking tape - cut to a shape and laid on top of the sheet behind it with a
soft shadow. These are the verbs for that, kept separate from the sets so a
new set is composition rather than new drawing code.

Deterministic throughout: textures are seeded from the caller's key, so a set
renders identically on every frame and on every run.
"""

from __future__ import annotations

import math
import zlib
from functools import lru_cache
from typing import Callable

from PIL import Image, ImageChops, ImageDraw, ImageFilter

RGB = tuple[int, int, int]


def seed_of(*parts) -> int:
    return zlib.crc32("|".join(map(str, parts)).encode()) & 0x7FFFFFFF


class Rng:
    """A small seeded generator, so a texture never changes between frames."""

    def __init__(self, *parts):
        self.state = seed_of(*parts) or 1

    def random(self) -> float:
        self.state = (1103515245 * self.state + 12345) & 0x7FFFFFFF
        return self.state / 0x7FFFFFFF

    def uniform(self, lo: float, hi: float) -> float:
        return lo + (hi - lo) * self.random()

    def choice(self, items):
        return items[int(self.random() * len(items)) % len(items)]


def shade(rgb: RGB, factor: float) -> RGB:
    return tuple(max(0, min(255, int(c * factor))) for c in rgb)


def mix(a: RGB, b: RGB, t: float) -> RGB:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def hexrgb(value: str) -> RGB:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


# --------------------------------------------------------------------------- #
# Texture
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=64)
def _grain(w: int, h: int, seed: int, mottle: float, tooth: float) -> Image.Image:
    """A greyscale paper texture centred on 128."""
    # effect_noise has no seed of its own; offsetting a larger field by the
    # seed gives distinct but stable textures per caller.
    big = Image.effect_noise((w + 64, h + 64), 64)
    ox, oy = seed % 61, (seed // 61) % 61
    fine = big.crop((ox, oy, ox + w, oy + h))
    slow = Image.effect_noise((max(2, w // 10), max(2, h // 10)), 70) \
        .resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(3))
    mixed = Image.blend(slow, fine, 0.4)
    return mixed.point(lambda v: int(128 + (v - 128) * (mottle + tooth) * 0.5))


def textured(w: int, h: int, rgb: RGB, *, key="", mottle: float = 0.5,
             tooth: float = 0.35) -> Image.Image:
    """A sheet of `rgb` card with paper grain, as RGBA."""
    w, h = max(1, int(w)), max(1, int(h))
    g = _grain(w, h, seed_of(key, w, h) % 3721, mottle, tooth)
    base = Image.new("RGB", (w, h), rgb)
    # Overlay-style modulation around mid grey: grain lifts and darkens the
    # colour by a few percent without shifting its hue.
    light = g.point(lambda v: max(0, v - 128) * 2)
    dark = g.point(lambda v: max(0, 128 - v) * 2)
    out = Image.composite(Image.new("RGB", (w, h), shade(rgb, 1.12)), base,
                          light.point(lambda v: int(v * 0.35)))
    out = Image.composite(Image.new("RGB", (w, h), shade(rgb, 0.84)), out,
                          dark.point(lambda v: int(v * 0.40)))
    return out.convert("RGBA")


def cut(mask: Image.Image, rgb: RGB, *, key="", mottle: float = 0.5) -> Image.Image:
    """Card in the shape of `mask` (an L image)."""
    sheet = textured(mask.width, mask.height, rgb, key=key, mottle=mottle)
    sheet.putalpha(mask)
    return sheet


def mask_of(w: int, h: int, fn: Callable[[ImageDraw.ImageDraw], None]) -> Image.Image:
    m = Image.new("L", (max(1, int(w)), max(1, int(h))), 0)
    fn(ImageDraw.Draw(m))
    return m


def rect(w, h, rgb, *, key="", radius: int = 0, mottle=0.5) -> Image.Image:
    return cut(mask_of(w, h, lambda d: d.rounded_rectangle(
        [0, 0, w - 1, h - 1], radius=radius, fill=255)), rgb, key=key or (w, h, rgb),
        mottle=mottle)


def ellipse(w, h, rgb, *, key="") -> Image.Image:
    return cut(mask_of(w, h, lambda d: d.ellipse([0, 0, w - 1, h - 1], fill=255)),
               rgb, key=key or ("e", w, h, rgb))


def poly(points, rgb, *, key="") -> tuple[Image.Image, int, int]:
    """Card in the shape of a polygon. Returns (image, x0, y0) to paste at."""
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    x0, y0 = int(min(xs)), int(min(ys))
    w, h = int(max(xs)) - x0 + 2, int(max(ys)) - y0 + 2
    local = [(x - x0, y - y0) for x, y in points]
    img = cut(mask_of(w, h, lambda d: d.polygon(local, fill=255)), rgb,
              key=key or ("p", tuple(points), rgb))
    return img, x0, y0


def torn_mask(w: int, h: int, *, key="", jag: float = 5.0,
              edges: str = "tblr", step: int = 14) -> Image.Image:
    """A rectangle whose chosen edges are torn rather than cut."""
    rng = Rng("torn", key, w, h)
    pts = []
    n = max(2, w // step)
    for i in range(n + 1):                            # top, left to right
        x = w * i / n
        pts.append((x, (rng.uniform(0, jag) if "t" in edges else 0)))
    m = max(2, h // step)
    for i in range(1, m + 1):                         # right, top to bottom
        y = h * i / m
        pts.append((w - (rng.uniform(0, jag) if "r" in edges else 0), y))
    for i in range(n - 1, -1, -1):                    # bottom, right to left
        x = w * i / n
        pts.append((x, h - (rng.uniform(0, jag) if "b" in edges else 0)))
    for i in range(m - 1, 0, -1):                     # left, bottom to top
        y = h * i / m
        pts.append(((rng.uniform(0, jag) if "l" in edges else 0), y))
    return mask_of(w, h, lambda d: d.polygon(pts, fill=255))


# --------------------------------------------------------------------------- #
# Composition
# --------------------------------------------------------------------------- #
def shadowed(img: Image.Image, *, offset=(6, 10), blur: int = 10,
             strength: float = 0.45, colour: RGB = (18, 10, 4)) -> Image.Image:
    """`img` on a transparent canvas with a soft drop shadow under it.

    The returned image is padded by the blur on every side; paste it at
    (x - pad, y - pad) where pad = blur * 2 + max offset, see `pad_for`.
    """
    pad = pad_for(offset, blur)
    w, h = img.width + 2 * pad, img.height + 2 * pad
    alpha = img.getchannel("A") if img.mode == "RGBA" else Image.new("L", img.size, 255)
    sh = Image.new("L", (w, h), 0)
    sh.paste(alpha.point(lambda a: int(a * strength)),
             (pad + offset[0], pad + offset[1]))
    if blur:
        sh = sh.filter(ImageFilter.GaussianBlur(blur))
    out = Image.new("RGBA", (w, h), (*colour, 0))
    out.putalpha(sh)
    out.alpha_composite(img.convert("RGBA"), (pad, pad))
    return out


def pad_for(offset=(6, 10), blur: int = 10) -> int:
    return blur * 2 + max(abs(offset[0]), abs(offset[1]))


def lay(canvas: Image.Image, img: Image.Image, x: float, y: float, *,
        shadow: bool = True, offset=(6, 10), blur: int = 10,
        strength: float = 0.45) -> tuple[int, int, int, int]:
    """Lay a cut piece on the canvas at (x, y), with its shadow. Returns its box."""
    x, y = int(x), int(y)
    if shadow:
        pad = pad_for(offset, blur)
        canvas.alpha_composite(shadowed(img, offset=offset, blur=blur,
                                        strength=strength), (x - pad, y - pad))
    else:
        canvas.alpha_composite(img, (x, y))
    return x, y, x + img.width, y + img.height


def rotated(img: Image.Image, degrees: float) -> Image.Image:
    if abs(degrees) < 0.01:
        return img
    return img.rotate(degrees, resample=Image.BICUBIC, expand=True)


def glow(canvas: Image.Image, cx: float, cy: float, radius: float, rgb: RGB,
         strength: float = 0.5) -> None:
    """Additive warm light, the lamp and window spill in the reference sets."""
    r = int(radius)
    m = Image.new("L", (2 * r, 2 * r), 0)
    ImageDraw.Draw(m).ellipse([0, 0, 2 * r - 1, 2 * r - 1], fill=int(255 * strength))
    m = m.filter(ImageFilter.GaussianBlur(r / 2.5))
    layer = Image.new("RGB", m.size, rgb)
    x0, y0 = int(cx - r), int(cy - r)
    region = canvas.crop((x0, y0, x0 + 2 * r, y0 + 2 * r)).convert("RGB")
    lit = ImageChops.screen(region, Image.composite(layer, Image.new("RGB", m.size, 0), m))
    lit = lit.convert("RGBA")
    lit.putalpha(canvas.crop((x0, y0, x0 + 2 * r, y0 + 2 * r)).getchannel("A"))
    canvas.paste(lit, (x0, y0))


def gradient(w: int, h: int, top: RGB, bottom: RGB) -> Image.Image:
    ramp = Image.linear_gradient("L").resize((w, h))
    return Image.composite(Image.new("RGB", (w, h), bottom),
                           Image.new("RGB", (w, h), top), ramp).convert("RGBA")


@lru_cache(maxsize=8)
def vignette(w: int, h: int, strength: float = 0.55) -> Image.Image:
    """An RGBA darkening layer, heaviest in the corners."""
    small = Image.new("L", (w // 8, h // 8), 0)
    d = ImageDraw.Draw(small)
    sw, shh = small.size
    d.ellipse([-sw * 0.25, -shh * 0.12, sw * 1.25, shh * 1.12], fill=255)
    m = small.filter(ImageFilter.GaussianBlur(sw / 7)).resize((w, h), Image.BICUBIC)
    alpha = m.point(lambda v: int((255 - v) * strength))
    layer = Image.new("RGBA", (w, h), (12, 6, 2, 0))
    layer.putalpha(alpha)
    return layer


@lru_cache(maxsize=8)
def grain_frames(w: int, h: int, count: int = 4, amount: int = 8) -> tuple:
    """Film grain, a few frames cycled so it shimmers without costing a
    noise field per frame.

    Light on purpose. Grain that changes every frame is the most expensive
    thing an encoder can be given: at 18 it made a reel 12 times the size of
    the flat style for a texture Instagram's own re-encode then removes. At 8
    it still lifts the flat colour off the screen. See REEL_STUDIO_CRF.
    """
    frames = []
    for i in range(count):
        n = Image.effect_noise((w // 2, h // 2), 40 + i).resize((w, h), Image.NEAREST)
        a = n.point(lambda v: int(abs(v - 128) / 128 * amount))
        light = Image.new("RGBA", (w, h), (255, 246, 230, 0))
        light.putalpha(a)
        frames.append(light)
    return tuple(frames)


def star(cx: float, cy: float, r_out: float, r_in: float, points: int = 5,
         rotation: float = -90) -> list[tuple[float, float]]:
    pts = []
    for i in range(points * 2):
        r = r_out if i % 2 == 0 else r_in
        a = math.radians(rotation + i * 180 / points)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts
