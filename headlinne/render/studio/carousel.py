"""The daily carousel in the studio style.

Same five slides doing the same five jobs as render/carousel.py - cover, scale,
twist, sources, cta, in that order, because the order is the argument - but
each one is now a scene rather than a page: a cut-paper set behind it, the
slide's kicker on a taped title strip, the words on torn paper cards, Pip as a
papercraft figure standing in the set, and the receipt on a paper ticket.

What does not change is what the slides say. The receipt is still the strict
agreement fraction drawn by theme.draw_receipt; a sensitive story still loses
Pip and his speech bubble on every slide; the scale slide's figure is still the
one generate/instagram.py verified.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from ...config import SLIDE_H, SLIDE_W, WEBSITE
from ...logging_setup import get_logger
from ...models import InstagramCarousel, Slide
from .. import fonts, pip as _pip, plate as plate_mod, theme
from . import direction, overlay, paper, sets, voxel

log = get_logger("render.studio.carousel")

MARGIN = 64
CARD_W = SLIDE_W - 2 * MARGIN
INK = overlay.INK
SOFT = (96, 84, 72)

TITLE_TOP = 34
CARD_TOP = 196
PIP_CELL = 14
PIP_FEET = (236, 1262)

# The set is 9:16 and a slide is 4:5: take a full-width band of it that puts
# the floor near the bottom of the slide, where Pip stands.
_CROP_TOP = 120


# --------------------------------------------------------------------------- #
# Ground
# --------------------------------------------------------------------------- #
def _background(spec: sets.SetSpec) -> Image.Image:
    built = sets.build(spec)
    crop_h = int(sets.SET_W * SLIDE_H / SLIDE_W)
    band = built.back.crop((0, _CROP_TOP, sets.SET_W, _CROP_TOP + crop_h))
    bg = band.resize((SLIDE_W, SLIDE_H), Image.LANCZOS)
    # A touch softer and darker than the reel: a slide is read, not watched,
    # and the cards on it carry paragraphs.
    bg = bg.filter(ImageFilter.GaussianBlur(2.2))
    bg.alpha_composite(paper.vignette(SLIDE_W, SLIDE_H, 0.6))
    return bg


def _sets_for(carousel: InstagramCarousel) -> dict[str, sets.SetSpec]:
    story = carousel.story
    sensitive = bool(getattr(story, "sensitive", False))
    text = " ".join(filter(None, [getattr(story, "title", ""),
                                  getattr(story, "summary", ""), carousel.title]))
    primary = direction.classify(text, carousel.category)
    if sensitive and primary not in sets.SOBER_SETS:
        primary = "maproom" if primary in ("street", "parliament", "harbour") else "newsroom"
    ring = (primary, *direction._NEIGHBOURS.get(primary, ("newsroom",)))
    if sensitive:
        ring = tuple(s for s in ring if s in sets.SOBER_SETS) or ("newsroom",)
    accent = tuple(theme.tone_for(story, category=carousel.category, role=""))
    variant = len(carousel.title) % 97
    trend = direction._trend(text)

    def spec(name, time="night"):
        if name in direction._EXTERIOR:
            time = "dusk"
        return sets.SetSpec(name=name, time=time, accent=accent, trend=trend,
                            variant=variant, sober=sensitive)

    return {
        "cover": spec(ring[0]),
        "scale": spec(ring[1 % len(ring)]),
        "twist": spec(ring[2 % len(ring)]),
        "sources": spec("newsroom"),
        "cta": spec("newsroom"),
    }


# --------------------------------------------------------------------------- #
# Paper pieces
# --------------------------------------------------------------------------- #
def _card(w: int, h: int, *, key, tape: bool = True) -> tuple[Image.Image, tuple[int, int]]:
    """A sheet of cream paper with torn edges, taped at the top corners.

    Returns the image and where the sheet's top-left sits inside it.
    """
    m = paper.torn_mask(w, h, key=("card", key), jag=4, edges="tblr", step=24)
    sheet = overlay._crumple(paper.cut(m, overlay.CREAM_PAPER, key=("cardpaper", key)), key)
    out = Image.new("RGBA", (w + 80, h + 60), (0, 0, 0, 0))
    out.alpha_composite(paper.shadowed(sheet, offset=(5, 12), blur=12, strength=0.5),
                        (40 - paper.pad_for((5, 12), 12), 30 - paper.pad_for((5, 12), 12)))
    if tape:
        out.alpha_composite(overlay.tape_piece(110, 44, key=(key, "l"), angle=28), (2, 0))
        out.alpha_composite(overlay.tape_piece(110, 44, key=(key, "r"), angle=-30),
                            (w + 80 - 140, 0))
    return out, (40, 30)


def _fit(text: str, width: int, height: int, *, start: int, minimum: int,
         weight: int = 800, max_lines: int = 5, body: bool = False):
    """The largest size at which `text` fits the box. (font, lines, line height)."""
    size = start
    while True:
        font = fonts.body_font(size, weight) if body else fonts.title_font(size, weight)
        lines = fonts.wrap_text(font, text, width)
        lh = int(size * (1.3 if body else 1.12))
        if (len(lines) <= max_lines and len(lines) * lh <= height) or size <= minimum:
            return font, lines[:max_lines], lh
        size -= 2


def _text_card(headline: str, body: str = "", *, key, head_start: int = 84,
               head_min: int = 50, max_h: int = 620, body_size: int = 38):
    """A card carrying a headline and a paragraph, sized to its content."""
    inner = CARD_W - 2 * 44
    hfont, hlines, hlh = _fit(headline, inner, max_h * 0.62, start=head_start,
                              minimum=head_min, max_lines=4)
    blines, blh, bfont = [], 0, None
    if body:
        room = max_h - 88 - len(hlines) * hlh - 24
        bfont, blines, blh = _fit(body, inner, max(room, body_size * 1.3),
                                  start=body_size, minimum=30, weight=500,
                                  max_lines=6, body=True)
    h = 44 + len(hlines) * hlh + (24 + len(blines) * blh if blines else 0) + 48
    card, (ox, oy) = _card(CARD_W, int(h), key=key)
    d = ImageDraw.Draw(card)
    y = oy + 40
    for line in hlines:
        d.text((ox + 44, y), line, font=hfont, fill=INK)
        y += hlh
    if blines:
        y += 24
        for line in blines:
            d.text((ox + 44, y), line, font=bfont, fill=SOFT)
            y += blh
    return paper.rotated(card, -0.6)


def _bubble(text: str, max_w: int = 520) -> Image.Image:
    """Pip's speech bubble, cut from white card with a tail to the left."""
    font = fonts.label_font(38, 700)
    lines = fonts.wrap_text(font, text, max_w - 60)[:3]
    lh = 48
    w = min(max_w, max(fonts.text_width(font, ln) for ln in lines) + 64)
    h = len(lines) * lh + 44
    img = Image.new("RGBA", (w + 40, h + 30), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([40, 0, 40 + w, h], radius=26, fill=(255, 252, 246, 255))
    d.polygon([(40, h - 46), (0, h + 18), (78, h - 22)], fill=(255, 252, 246, 255))
    for i, line in enumerate(lines):
        d.text((72, 22 + i * lh), line, font=font, fill=INK)
    return paper.shadowed(img, offset=(4, 8), blur=8, strength=0.4)


def _receipt_ticket(story, *, names: bool, width: int = 560) -> Image.Image:
    """The source strip on a paper ticket."""
    probe = Image.new("RGBA", (width, 400))
    end = theme.draw_receipt(probe, ImageDraw.Draw(probe), story, x=36, y=34,
                             names=names, label_size=32, name_size=26)
    h = end + 30
    card, (ox, oy) = _card(width, h, key=("receipt", getattr(story, "url", "")),
                           tape=False)
    theme.draw_receipt(card, ImageDraw.Draw(card), story, x=ox + 36, y=oy + 34,
                       names=names, label_size=32, name_size=26)
    return paper.rotated(card, 0.9)


def _pip_grid(pose: str) -> str:
    if pose in _pip.SPRITES:
        return _pip.SPRITES[pose]
    if pose in theme.CYCLES:
        return theme.CYCLES[pose]()[0]
    return _pip.SPRITES["idle"]


def _place_pip(canvas: Image.Image, slide: Slide, spec: sets.SetSpec, *,
               feet=PIP_FEET, cell: int = PIP_CELL) -> tuple[int, int, int, int] | None:
    if not slide.pose:
        return None
    hat = direction._SET_HAT.get(spec.name, "")
    fig = voxel.figure(_pip_grid(slide.pose), cell=cell, hat=hat)
    fx, fy = feet
    shadow = voxel.contact_shadow(int(fig.width * 0.72))
    canvas.alpha_composite(shadow, (fx - shadow.width // 2, fy - shadow.height // 2))
    x, y = fx - fig.width // 2, fy - fig.height + int(cell * 0.6)
    canvas.alpha_composite(fig, (x, y))
    return x, y, x + fig.width, fy


def _say(canvas: Image.Image, slide: Slide, pip_box) -> None:
    if not slide.say or pip_box is None:
        return
    bubble = _bubble(slide.say)
    x = pip_box[2] - 30
    y = max(CARD_TOP, pip_box[1] + 10)
    x = min(x, SLIDE_W - MARGIN - bubble.width + 20)
    canvas.alpha_composite(bubble, (x, y))


def _title(canvas: Image.Image, text: str) -> int:
    strip = overlay.title(text, max_w=SLIDE_W - 2 * MARGIN + 30)
    x = (SLIDE_W - strip.width) // 2
    canvas.alpha_composite(strip, (x, TITLE_TOP))
    return TITLE_TOP + strip.height - 20


# --------------------------------------------------------------------------- #
# The five slides
# --------------------------------------------------------------------------- #
def _cover(slide, carousel, story, spec, loader):
    canvas = _background(spec)
    _title(canvas, slide.kicker or theme.label_for(carousel.category))
    card = _text_card(slide.headline, slide.subtitle, key=("cover", slide.headline),
                      head_start=92, head_min=54, max_h=620)
    canvas.alpha_composite(card, (MARGIN - 40, CARD_TOP))
    box = _place_pip(canvas, slide, spec)
    if story is not None:
        ticket = _receipt_ticket(story, names=False, width=520)
        canvas.alpha_composite(ticket, (SLIDE_W - MARGIN - ticket.width + 30,
                                        SLIDE_H - ticket.height - 40))
    elif box is not None:
        _say(canvas, slide, box)
    return canvas


def _scale(slide, carousel, story, spec, loader):
    canvas = _background(spec)
    _title(canvas, slide.kicker or "HOW BIG")
    y = CARD_TOP
    figure = (slide.figure or "").strip()
    if figure:
        stat = _big_stat(figure, slide.unit or "")
        canvas.alpha_composite(stat, (MARGIN - 40, y))
        y += stat.height - 30
    note = _text_card(slide.explanation or slide.headline, key=("scale", slide.headline),
                      head_start=50 if figure else 64, head_min=38,
                      max_h=420 if figure else 560)
    canvas.alpha_composite(note, (MARGIN - 40, y))
    y += note.height - 20
    room = SLIDE_H - 40 - y
    plate_img = None
    if story is not None and room >= 300:
        ph = min(380, room - 20)
        plate_img, _rung = plate_mod.for_story(story, loader, width=int(ph * 1.47),
                                               height=ph)
    if plate_img is not None:
        if plate_img.height > room:
            r = room / plate_img.height
            plate_img = plate_img.resize((int(plate_img.width * r), room), Image.LANCZOS)
        canvas.alpha_composite(plate_img, (SLIDE_W - MARGIN - plate_img.width + 20,
                                           SLIDE_H - 30 - plate_img.height))
    elif room >= 380:
        _place_pip(canvas, slide, spec)
    return canvas


def _big_stat(figure: str, unit: str) -> Image.Image:
    """The scale slide's figure on a stat card, the reel's card at slide size."""
    nf = fonts.title_font(200, 800)
    uf = fonts.title_font(54, 800)
    badge = overlay.badge(150)
    fw = fonts.text_width(nf, figure)
    uw = fonts.text_width(uf, unit) if unit else 0
    w = min(CARD_W, 44 + badge.width + 34 + fw + (24 + uw if unit else 0) + 50)
    h = 250
    card, (ox, oy) = _card(w, h, key=("stat", figure, unit))
    d = ImageDraw.Draw(card)
    card.alpha_composite(badge, (ox + 40, oy + 46))
    x = ox + 44 + badge.width + 34
    d.text((x, oy + 4), figure, font=nf, fill=INK)
    if unit:
        d.text((x + fw + 24, oy + 150), unit, font=uf, fill=SOFT)
    return paper.rotated(card, -1.0)


def _twist(slide, carousel, story, spec, loader):
    canvas = _background(spec)
    _title(canvas, slide.kicker or "WHAT YOU DID NOT KNOW")
    card = _text_card(slide.headline, slide.explanation, key=("twist", slide.headline),
                      head_start=80, head_min=48, max_h=700)
    canvas.alpha_composite(card, (MARGIN - 40, CARD_TOP))
    bottom = CARD_TOP + card.height
    if SLIDE_H - bottom >= 380:
        box = _place_pip(canvas, slide, spec)
        _say(canvas, slide, box)
    return canvas


def _sources(slide, carousel, story, spec, loader):
    canvas = _background(spec)
    _title(canvas, slide.kicker or "SOURCES")
    y = CARD_TOP
    if story is not None:
        ticket = _receipt_ticket(story, names=True, width=CARD_W)
        canvas.alpha_composite(ticket, (MARGIN - 40, y))
        y += ticket.height - 10
    note = _text_card(slide.explanation or
                      "Headlinne reads every outlet covering a story and shows "
                      "you where they agree, and where they do not.",
                      key=("sources", slide.headline), head_start=44, head_min=34,
                      max_h=360)
    canvas.alpha_composite(note, (MARGIN - 40, y))
    if SLIDE_H - (y + note.height) >= 360:
        _place_pip(canvas, slide, spec, feet=(SLIDE_W - 250, PIP_FEET[1]))
    return canvas


def _cta(slide, carousel, story, spec, loader):
    canvas = _background(spec)
    _title(canvas, slide.kicker or "READ THE FULL STORY")
    box = overlay.comment_box(WEBSITE.lower(), 1.0, width=CARD_W)
    canvas.alpha_composite(box, ((SLIDE_W - box.width) // 2, CARD_TOP + 10))
    note = _text_card(slide.subtitle or "Every source on this story, side by "
                      "side. Free to read, no account needed.",
                      key=("cta", slide.headline), head_start=46, head_min=34,
                      max_h=300)
    y = CARD_TOP + box.height + 10
    canvas.alpha_composite(note, (MARGIN - 40, y))
    pip_box = _place_pip(canvas, slide, spec, cell=16)
    if story is not None:
        ticket = _receipt_ticket(story, names=False, width=500)
        canvas.alpha_composite(ticket, (SLIDE_W - MARGIN - ticket.width + 30,
                                        SLIDE_H - ticket.height - 40))
    elif pip_box is not None:
        _say(canvas, slide, pip_box)
    return canvas


_RENDERERS = {"cover": _cover, "scale": _scale, "twist": _twist,
              "sources": _sources, "cta": _cta}


def render_carousel(carousel: InstagramCarousel, out_dir: Path, loader) -> list[Path]:
    """Render every slide to a PNG in the studio style."""
    out_dir.mkdir(parents=True, exist_ok=True)
    story = carousel.story
    specs = _sets_for(carousel)
    sensitive = bool(getattr(story, "sensitive", False))
    paths: list[Path] = []
    for i, slide in enumerate(carousel.slides, 1):
        if sensitive:
            # The second lock: generate/instagram.py clears these too.
            slide.pose, slide.say = "", ""
        spec = specs.get(slide.role, specs["cover"])
        render = _RENDERERS.get(slide.role, _twist)
        img = render(slide, carousel, story, spec, loader)
        path = out_dir / f"slide_{i}.png"
        img.convert("RGB").save(path, "PNG")
        slide.image_file = str(path)
        paths.append(path)
        log.info("rendered %s (%s, studio, %s set)", path.name, slide.role, spec.name)
    return paths
