"""X cards at 1200x675, ported from design/prototypes/xpost.py.

On X the post text is the hook and the image is the evidence, so the card never
repeats the headline - it carries the proof. Five types, each saying something
only this pipeline can say:

  receipt  - who reported it and whether they agree
  compare  - two outlets, two numbers, the same document
  correct  - what was reported against what turned out to be true
  photo    - the story's image, or a drawn scene, plus one fact
  cta      - the reply that closes a thread
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from ..config import INK, SURFACE, TEXT_SECONDARY, WEBSITE
from . import fonts, plate, theme

W, H, M = 1200, 675, 56

CORAL = (206, 62, 34)
RAISED = (255, 253, 248)


def _rgb(value: str) -> tuple[int, int, int]:
    return theme.hex_to_rgb(value)


def font(px: int, weight: int = 800):
    return fonts.label_font(px, weight)


def _page() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    canvas = Image.new("RGBA", (W, H), _rgb(SURFACE))
    return canvas, ImageDraw.Draw(canvas)


def chrome(draw: ImageDraw.ImageDraw, tone, label: str) -> None:
    """Wordmark, the card's own label, one rule, and the domain at the foot."""
    ink, soft = _rgb(INK), _rgb(TEXT_SECONDARY)
    draw.text((M, 40), "HEADLINNE", font=font(28, 800), fill=ink)
    draw.text((W - M, 42), label.upper(), font=font(20, 700), fill=tone,
              anchor="ra")
    draw.rectangle([M, 84, W - M, 87], fill=tone)
    draw.text((M, H - 46), WEBSITE.lower(), font=font(20, 600), fill=soft)


def receipt_card(*, outlets: list[str], agree: int | None = None,
                 tone=None) -> Image.Image:
    """Who reported it. The names are the argument, so they are the content."""
    tone = tone if tone is not None else theme.accent_for("Finance")
    agree = len(outlets) if agree is None else agree
    canvas, draw = _page()
    ink = _rgb(INK)
    chrome(draw, tone, "Sources")
    draw.text((M, 132), f"{agree} of {len(outlets)} outlets agree",
              font=font(66, 800), fill=ink)
    for i, name in enumerate(outlets):
        x = M + (i % 2) * 480
        y = 236 + (i // 2) * 62
        draw.rectangle([x, y, x + 13, y + 40], fill=tone)
        draw.text((x + 30, y + 2), name, font=font(30, 600), fill=ink)
    pw, ph = theme.pip_size("verified", 8)
    theme.draw_pip(canvas, "verified", x=W - M - pw, y=H - 60 - ph, scale=8)
    return canvas


def compare_card(*, headline: str, left: tuple[str, str, str],
                 right: tuple[str, str, str], note: str, tone=None) -> Image.Image:
    """Two outlets, two numbers, one document. The gap is the story."""
    tone = tone if tone is not None else theme.accent_for("Geopolitics")
    canvas, draw = _page()
    ink, soft = _rgb(INK), _rgb(TEXT_SECONDARY)
    chrome(draw, tone, "Sources disagree")
    draw.text((M, 128), headline, font=font(52, 800), fill=ink)
    for i, (who, num, unit) in enumerate((left, right)):
        x = M + i * 560
        draw.rectangle([x, 214, x + 500, 470], fill=RAISED)
        draw.rectangle([x, 214, x + 500, 470], outline=ink, width=4)
        draw.text((x + 26, 238), who.upper(), font=font(22, 700), fill=tone)
        draw.text((x + 26, 276), num, font=font(96, 800), fill=ink)
        draw.text((x + 26, 392), unit, font=font(26, 500), fill=soft)
    draw.text((M, 506), note, font=font(30, 600), fill=soft)
    pw, ph = theme.pip_size("puzzled", 8)
    theme.draw_pip(canvas, "puzzled", x=W - M - pw, y=H - 52 - ph, scale=8)
    return canvas


def correct_card(*, rows: list[tuple[str, str, bool]], note: str,
                 tone=CORAL) -> Image.Image:
    """What was reported against what turned out to be true.

    The struck row keeps its rule in the correction colour: the point is not
    that the first line was deleted but that it was believed.
    """
    canvas, draw = _page()
    ink, soft = _rgb(INK), _rgb(TEXT_SECONDARY)
    good = theme.accent_for("Finance")
    chrome(draw, tone, "Correction")
    y = 148
    for label, text, struck in rows:
        col = tone if struck else good
        draw.text((M, y), label.upper(), font=font(22, 700), fill=col)
        fnt = font(46, 750)
        draw.text((M, y + 38), text, font=fnt, fill=soft if struck else ink)
        if struck:
            tw = draw.textlength(text, font=fnt)
            draw.rectangle([M, y + 62, M + tw, y + 66], fill=tone)
        y += 176
    draw.text((M, 524), note, font=font(26, 500), fill=soft)
    pw, ph = theme.pip_size("read", 8)
    theme.draw_pip(canvas, "read", x=W - M - pw, y=H - 52 - ph, scale=8)
    return canvas


def photo_card(*, label: str, number: str, unit: str, body: str,
               category: str = "Science", scene: Image.Image | None = None,
               caption: str = "ILLUSTRATION · NOT A PHOTOGRAPH",
               tone=None) -> Image.Image:
    """The story's image - or a drawn scene when there is none - plus one fact."""
    tone = tone if tone is not None else theme.accent_for("Technology")
    canvas, draw = _page()
    ink, soft = _rgb(INK), _rgb(TEXT_SECONDARY)
    chrome(draw, tone, label)
    art = scene if scene is not None else plate.scene_for(category, w=460, h=300)
    tile = plate.tilted(art, angle=-3.0, caption=caption,
                        font=font(18, 600))
    tile.thumbnail((520, 420), Image.LANCZOS)
    canvas.alpha_composite(tile.convert("RGBA"), (W - M - tile.width, 122))
    draw.text((M, 150), number, font=font(110, 800), fill=tone)
    draw.text((M, 282), unit, font=font(34, 600), fill=ink)
    for i, line in enumerate(fonts.wrap_text(font(28, 450), body, 520)):
        draw.text((M, 350 + i * 38), line, font=font(28, 450), fill=soft)
    _, ph = theme.pip_size("idle", 7)
    theme.draw_pip(canvas, "idle", x=M, y=H - 52 - ph, scale=7)
    return canvas


def cta_card(*, lines: tuple[str, str], sources: int = 8,
             agree: int | None = None, tone=None) -> Image.Image:
    """The reply that closes every X thread. The domain is the loudest thing."""
    tone = tone if tone is not None else theme.accent_for("Technology")
    agree = sources if agree is None else agree
    canvas, draw = _page()
    ink, soft = _rgb(INK), _rgb(TEXT_SECONDARY)
    good = theme.accent_for("Finance")
    chrome(draw, tone, "Read it")
    draw.text((M, 138), WEBSITE.lower(), font=font(88, 800), fill=ink)
    draw.text((M, 254), lines[0], font=font(34, 500), fill=soft)
    draw.text((M, 306), lines[1], font=font(34, 500), fill=soft)
    for i in range(sources):
        bx = M + i * 22
        draw.rectangle([bx, 396, bx + 13, 438], fill=good)
    draw.text((M + 200, 400), f"{agree} of {sources} outlets agree",
              font=font(30, 700), fill=ink)
    pw, ph = theme.pip_size("carry", 9)
    theme.draw_pip(canvas, "carry", x=W - M - pw, y=H - 66 - ph, scale=9)
    return canvas
