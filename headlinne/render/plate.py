"""Image plates, and the fallback ladder for when there is no usable photograph.

A straight rectangle reads as a screenshot. A tilted one, in a paper frame with
a strip of tape, reads as an object someone put there - which is the difference
between a post that looks generated and one that looks made.

The ladder, in order. Every rung produces a designed object; none of them is a
bare gradient, because a bare gradient is what the old carousel fell back to on
roughly half its slides:

  1. the article's own photograph, via news.images.best_story_image()
  2. a generated pixel scene keyed to the category
  3. a generated chart plate built from figures in the story
  4. no plate at all - Pip presents the headline, larger type, more air

Rung 2 always carries "ILLUSTRATION - NOT A PHOTOGRAPH". That caption lives
inside tilted() rather than at the call site so it cannot be forgotten: this
brand is built on showing its working, and a drawn crater mistaken for a NASA
image would cost more trust in one post than the source strip earns in a month.
"""

from __future__ import annotations

import hashlib
import random
from typing import Callable, Optional

from PIL import Image, ImageDraw, ImageFilter

from ..logging_setup import get_logger
from . import fonts

log = get_logger("render.plate")

PAPER = (247, 241, 230)
FRAME = (255, 253, 248)
INK = (25, 19, 16)
INK_SOFT = (110, 97, 86)
TERRA = (196, 86, 47)
MARIGOLD = (148, 98, 23)
MINT = (30, 107, 84)
NIGHT = (23, 20, 30)
DUST = (168, 158, 146)
DUST_HI = (206, 197, 184)
DUST_LO = (108, 100, 92)

ILLUSTRATION_CAPTION = "ILLUSTRATION · NOT A PHOTOGRAPH"

# Below this a source photo is too soft to sit inside a frame that draws
# attention to it. Under it we drop to a generated rung rather than enlarging a
# thumbnail, because a blurred photo in a paper frame reads as a mistake.
MIN_PHOTO_PX = 320


def tilted(img: Image.Image, angle: float = -3.2, border: int = 18,
           shadow: bool = True, tape: bool = True,
           caption: Optional[str] = None, font=None,
           bg=PAPER) -> Image.Image:
    """A photo in a paper frame, rotated slightly.

    The tilt is the whole point: a straight rectangle reads as a screenshot, a
    tilted one reads as an object.
    """
    img = img.convert("RGB")
    w, h = img.size
    cap_h = 54 if caption else 0
    if caption and font is None:
        font = fonts.label_font(22, weight=600)

    plate = Image.new("RGB", (w + border * 2, h + border * 2 + cap_h), FRAME)
    plate.paste(img, (border, border))
    d = ImageDraw.Draw(plate)
    d.rectangle([0, 0, plate.width - 1, plate.height - 1], outline=INK, width=4)
    if caption:
        d.text((border, h + border + 14), caption, font=font, fill=INK_SOFT)

    rot = plate.convert("RGBA").rotate(angle, expand=True, resample=Image.BICUBIC)
    out = Image.new("RGBA", (rot.width + 30, rot.height + 30), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", rot.size, (0, 0, 0, 0))
        sh.paste((0, 0, 0, 70), (0, 0), rot.split()[-1])
        sh = sh.filter(ImageFilter.GaussianBlur(9))
        out.paste(sh, (14, 16), sh)
    out.paste(rot, (0, 0), rot)

    if tape:                               # a strip of masking tape, top-left
        t = Image.new("RGBA", (86, 30), (222, 210, 186, 218))
        td = ImageDraw.Draw(t)
        td.line([(0, 0), (86, 0)], fill=(200, 186, 160, 235), width=2)
        t = t.rotate(angle - 16, expand=True, resample=Image.BICUBIC)
        out.paste(t, (int(out.width * 0.16), 2), t)
    return out


# --------------------------------------------------------------------------- #
# Rung 2: generated pixel scenes, one per category
# --------------------------------------------------------------------------- #
def _px(d, x, y, s, c):
    d.rectangle([x, y, x + s - 1, y + s - 1], fill=c)


def moon_scene(w=560, h=380, seed=5, px=8):
    """Lunar surface with an impact crater.

    Obviously an illustration - which is the point. It must never be mistaken
    for a photograph.
    """
    rnd = random.Random(seed)
    im = Image.new("RGB", (w, h), NIGHT)
    d = ImageDraw.Draw(im)
    for y in range(0, int(h * 0.54), 2):          # sky falls off toward horizon
        k = y / (h * 0.54)
        d.rectangle([0, y, w, y + 2],
                    fill=(int(23 + 26 * k), int(20 + 22 * k), int(30 + 26 * k)))
    for _ in range(46):                                    # stars
        sx, sy = rnd.randrange(0, w, px), rnd.randrange(0, int(h * 0.5), px)
        _px(d, sx, sy, px, (200, 196, 210) if rnd.random() > .35 else (120, 116, 132))

    horizon = int(h * 0.52)
    d.rectangle([0, horizon, w, h], fill=DUST)
    for y in range(horizon, h, 2):                # regolith brightens to camera
        k = (y - horizon) / max(1, h - horizon)
        d.rectangle([0, y, w, y + 2], fill=(int(168 + 30 * k), int(158 + 28 * k),
                                            int(146 + 26 * k)))
    for x in range(0, w, px):                              # regolith texture
        wob = int(6 * px * (0.5 + 0.5 * rnd.random()))
        d.rectangle([x, horizon, x + px, horizon + px], fill=DUST_HI)
        if rnd.random() > .72:
            _px(d, x, horizon + wob, px, DUST_LO)

    cx, cy, r = int(w * 0.58), int(h * 0.76), int(w * 0.17)
    d.ellipse([cx - r, cy - r // 2, cx + r, cy + r // 2], fill=DUST_LO)
    d.ellipse([cx - r + px, cy - r // 2 + px, cx + r - px, cy + r // 2 - px],
              fill=(74, 68, 62))
    d.ellipse([cx - r, cy - r // 2, cx + r, cy + r // 2], outline=DUST_HI, width=px // 2)
    for _ in range(22):                                    # ejecta
        a = rnd.random() * 6.283
        dist = r + rnd.randrange(px, r)
        ex = cx + int(dist * 1.4 * (a - 3.14) / 3.14)
        ey = cy + int(dist * 0.34 * (rnd.random() - 0.5))
        if 0 < ex < w and horizon < ey < h:
            _px(d, ex - ex % px, ey - ey % px, px, DUST_HI)
    return im


def city_scene(w=560, h=380, seed=3, px=8):
    """A skyline at dusk, for stories with no natural object to draw.

    Geopolitics and finance rarely have a photographable *thing* at their
    centre, and drawing a flag or a trading floor would editorialise. A skyline
    says "somewhere people live" and claims nothing else.
    """
    rnd = random.Random(seed)
    im = Image.new("RGB", (w, h), (38, 32, 44))
    d = ImageDraw.Draw(im)
    for y in range(0, h, 2):                     # dusk gradient
        k = y / h
        d.rectangle([0, y, w, y + 2], fill=(int(38 + 120 * k), int(32 + 70 * k),
                                            int(44 + 40 * k)))
    ground = int(h * 0.86)
    x = 0
    while x < w:
        bw = rnd.randrange(4, 9) * px
        bh = rnd.randrange(int(h * 0.18), int(h * 0.55))
        top = ground - bh
        shade = rnd.choice([(46, 38, 42), (58, 47, 50), (36, 30, 36)])
        d.rectangle([x, top, x + bw, ground], fill=shade)
        for wy in range(top + px, ground - px, px * 2):    # lit windows
            for wx in range(x + px, x + bw - px, px * 2):
                if rnd.random() > .62:
                    _px(d, wx, wy, px, (236, 196, 120) if rnd.random() > .3
                        else (176, 146, 96))
        x += bw + px
    d.rectangle([0, ground, w, h], fill=(28, 23, 28))
    return im


def chart_scene(w=560, h=380, series=(3, 5, 4, 7, 9, 8, 12), px=8,
                highlight_last: bool = True):
    """Rung 3: a story with a number but no picture.

    The bars carry direction, not a claim: only the caller's caption states
    where the figures came from, and generate/reel.py verifies every printed
    figure against the source article before it is allowed on screen.
    """
    im = Image.new("RGB", (w, h), (240, 232, 216))
    d = ImageDraw.Draw(im)
    pad, top = 40, 40
    series = tuple(series) or (1,)
    bw = max(1, (w - pad * 2) // len(series))
    peak = max(series) or 1
    for i, v in enumerate(series):
        bh = int((h - top - pad) * v / peak)
        x = pad + i * bw
        col = MARIGOLD if (highlight_last and i == len(series) - 1) else TERRA
        d.rectangle([x, h - pad - bh, x + bw - 10, h - pad], fill=col)
    d.rectangle([pad, h - pad, w - pad, h - pad + 4], fill=INK)
    return im


SCENES: dict[str, Callable[..., Image.Image]] = {
    "Space": moon_scene,
    "Science": moon_scene,
    "Technology": chart_scene,
    "Finance": chart_scene,
    "Geopolitics": city_scene,
}


def scene_for(category: str, **kw) -> Image.Image:
    return SCENES.get(category, chart_scene)(**kw)


# --------------------------------------------------------------------------- #
# The ladder
# --------------------------------------------------------------------------- #
def _seed_for(text: str) -> int:
    """A stable per-story seed, so one story's scene never changes between runs
    while two different stories on the same day do not share one."""
    return int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)


def _fit(img: Image.Image, w: int, h: int) -> Image.Image:
    """Cover-fit to exactly w x h, then sharpen - the same treatment photography
    gets everywhere else in the system."""
    from . import theme
    return theme.cover_fit(img, w, h).convert("RGB")


def for_story(story, loader=None, *, width: int = 560, height: int = 380,
              angle: float = -3.2) -> tuple[Optional[Image.Image], str]:
    """The best plate available for a story, and which rung produced it.

    Returns (plate, rung) where rung is "photo" | "scene" | "chart" | "none".
    A "none" rung is not a failure: it is the instruction to the caller to give
    the headline more room and let Pip present it, which is rung 4.

    Sensitive stories never get a generated scene. Drawing a pixel illustration
    beside a disaster is the exact tonal failure the sober template exists to
    prevent, so they take the photo if there is one and nothing if there is not.
    """
    caption_font = fonts.label_font(22, weight=600)
    sensitive = bool(getattr(story, "sensitive", False))

    # Rung 1: the article's own photograph.
    if loader is not None and getattr(story, "image_url", None):
        try:
            img = loader(story.image_url)
        except Exception as exc:                    # pragma: no cover - network
            log.warning("plate photo load failed: %s", exc)
            img = None
        if img is not None and min(img.size) >= MIN_PHOTO_PX:
            source = getattr(story, "source", "") or ""
            return tilted(_fit(img, width, height), angle=angle,
                          caption=source.upper() if source else None,
                          font=caption_font), "photo"
        if img is not None:
            log.info("plate photo %dx%d is too soft to frame, dropping a rung",
                     *img.size)

    if sensitive:
        return None, "none"

    # Rung 3 before rung 2 when the story is really about a number: a chart of
    # the actual figures says more than a decorative scene.
    figures = _figures_in(story)
    category = getattr(story, "category", "") or ""
    if len(figures) >= 3 and category in ("Finance", "Technology"):
        return tilted(chart_scene(width, height, series=figures), angle=angle,
                      caption="SOURCE: FIGURES IN THE ARTICLE",
                      font=caption_font), "chart"

    # Rung 2: a generated scene, always captioned as an illustration.
    if category in SCENES:
        scene = scene_for(category, w=width, h=height,
                          seed=_seed_for(getattr(story, "title", "") or category))
        return tilted(scene, angle=angle, caption=ILLUSTRATION_CAPTION,
                      font=caption_font), "scene"

    # Rung 4.
    return None, "none"


_MAX_CHART_BARS = 7


def _figures_in(story) -> tuple[int, ...]:
    """Comparable magnitudes named in the story, for the chart rung."""
    from ..news.corroborate import _figures

    text = f"{getattr(story, 'title', '')} {getattr(story, 'summary', '')}"
    values = [v for v, _unit, _ctx in _figures(text) if v > 0]
    return tuple(int(v) for v in values[:_MAX_CHART_BARS])
