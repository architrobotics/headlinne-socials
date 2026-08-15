"""Image plates for reels and cards, plus the fallback chain when there is no
usable photograph.

Chain, in order:
  1. the article's own image, tilted in a paper frame
  2. a generated pixel scene keyed to the category  (this file)
  3. a typographic plate - the number, set large
  4. Pip presenting the headline, no plate at all

Never a bare gradient. Every rung of the ladder is a designed object.
"""
import random
from PIL import Image, ImageDraw, ImageFilter

PAPER = (247, 241, 230)
FRAME = (255, 253, 248)
INK = (25, 19, 16)
INK_SOFT = (110, 97, 86)
TERRA = (196, 86, 47)
MARIGOLD = (201, 133, 32)
MINT = (30, 107, 84)
NIGHT = (23, 20, 30)
DUST = (168, 158, 146)
DUST_HI = (206, 197, 184)
DUST_LO = (108, 100, 92)


def tilted(img, angle=-3.2, border=18, shadow=True, tape=True,
           caption=None, font=None, bg=PAPER):
    """A photo in a paper frame, rotated slightly. The tilt is the whole point:
    a straight rectangle reads as a screenshot, a tilted one reads as an object."""
    w, h = img.size
    plate = Image.new("RGB", (w + border * 2, h + border * 2 + (54 if caption else 0)),
                      FRAME)
    plate.paste(img, (border, border))
    d = ImageDraw.Draw(plate)
    d.rectangle([0, 0, plate.width - 1, plate.height - 1], outline=INK, width=4)
    if caption and font:
        d.text((border, h + border + 14), caption, font=font, fill=INK_SOFT)

    rot = plate.convert("RGBA").rotate(angle, expand=True,
                                       resample=Image.BICUBIC)
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
# Fallback rung 2: generated pixel scenes, one per category
# --------------------------------------------------------------------------- #
def _px(d, x, y, s, c):
    d.rectangle([x, y, x + s - 1, y + s - 1], fill=c)


def moon_scene(w=560, h=380, seed=5, px=8):
    """Lunar surface with an impact crater. Obviously an illustration - which is
    the point. It must never be mistaken for a photograph."""
    rnd = random.Random(seed)
    im = Image.new("RGB", (w, h), NIGHT)
    d = ImageDraw.Draw(im)
    for y in range(0, int(h * 0.54), 2):          # sky falls off toward the horizon
        k = y / (h * 0.54)
        d.rectangle([0, y, w, y + 2],
                    fill=(int(23 + 26 * k), int(20 + 22 * k), int(30 + 26 * k)))
    for _ in range(46):                                    # stars
        sx, sy = rnd.randrange(0, w, px), rnd.randrange(0, int(h * 0.5), px)
        _px(d, sx, sy, px, (200, 196, 210) if rnd.random() > .35 else (120, 116, 132))

    horizon = int(h * 0.52)
    d.rectangle([0, horizon, w, h], fill=DUST)
    for y in range(horizon, h, 2):                # regolith brightens toward camera
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


def chart_scene(w=560, h=380, series=(3, 5, 4, 7, 9, 8, 12), px=8):
    """Fallback for a story with a number but no picture."""
    im = Image.new("RGB", (w, h), (240, 232, 216))
    d = ImageDraw.Draw(im)
    pad, top = 40, 40
    bw = (w - pad * 2) // len(series)
    peak = max(series)
    for i, v in enumerate(series):
        bh = int((h - top - pad) * v / peak)
        x = pad + i * bw
        col = TERRA if i < len(series) - 1 else MARIGOLD
        d.rectangle([x, h - pad - bh, x + bw - 10, h - pad], fill=col)
    d.rectangle([pad, h - pad, w - pad, h - pad + 4], fill=INK)
    return im


SCENES = {"Space": moon_scene, "Science": moon_scene, "Finance": chart_scene,
          "Technology": chart_scene}


def scene_for(category: str, **kw):
    return SCENES.get(category, chart_scene)(**kw)


if __name__ == "__main__":
    from PIL import ImageFont
    import pathlib
    F = pathlib.Path("C:/Users/khand/Downloads/socials/assets/fonts/Manrope-Variable.ttf")
    f = ImageFont.truetype(str(F), 22)
    try:
        f.set_variation_by_axes([600])
    except Exception:
        pass

    sheet = Image.new("RGB", (1300, 470), PAPER)
    x = 30
    for name, im in (("moon", moon_scene()), ("chart", chart_scene())):
        t = tilted(im, angle=-3.4 if name == "moon" else 2.6,
                   caption="ILLUSTRATION · NOT A PHOTOGRAPH" if name == "moon"
                   else "SOURCE: FIGURES IN THE ARTICLE", font=f)
        sheet.paste(t, (x, 30), t)
        x += t.width + 40
    sheet.save("sheet_plates.png")
    moon_scene().save("plate_moon.png")
    print("plates rendered")
