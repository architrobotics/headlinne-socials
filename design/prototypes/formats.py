"""Pip across every format: card, carousel, reel. Built on a real story.

Story: a Falcon 9 second stage hit the Moon near Einstein Crater on 5 Aug 2026
at 8,700 km/h. Four tonnes, school-bus sized, ~3 tonnes of TNT. NASA's LRO and
South Korea's Danuri repositioned to photograph it. Only the second known
accidental rocket impact - and the first, in March 2022, was blamed on SpaceX
before it turned out to be a Chinese Long March 3C.
"""
import base64, io, pathlib
from PIL import Image, ImageDraw, ImageFont
import pip as P

FONTS = pathlib.Path("C:/Users/khand/Downloads/socials/assets/fonts")

PAPER, PAPER_DEEP = (247, 241, 230), (233, 223, 206)
INK, INK_SOFT     = (25, 19, 16), (110, 97, 86)
TERRA, MINT       = (196, 86, 47), (30, 107, 84)
MARIGOLD, CORAL   = (148, 98, 23), (206, 62, 34)
NIGHT             = (23, 18, 14)
CREAM             = (245, 239, 228)


def font(px, weight=800):
    f = ImageFont.truetype(str(FONTS / "Manrope-Variable.ttf"), px)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f


def wrap(d, text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if d.textlength(t, font=fnt) <= max_w:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def block(d, text, fnt, x, y, max_w, lh, fill):
    for ln in wrap(d, text, fnt, max_w):
        d.text((x, y), ln, font=fnt, fill=fill)
        y += lh
    return y


def bubble(im, d, text, x, y, max_w, tail="left", fill=CREAM, ink=INK, size=34):
    """Comic speech bubble with a pixel-stepped edge and a tail toward Pip."""
    f = font(size, 650)
    lines = wrap(d, text, f, max_w - 44)
    tw = max(d.textlength(l, font=f) for l in lines)
    w, h = int(tw) + 44, len(lines) * int(size * 1.34) + 34
    d.rectangle([x, y, x + w, y + h], fill=fill)
    for off in (0, 3):                                  # chunky pixel border
        d.rectangle([x - off, y - off, x + w + off, y + h + off],
                    outline=ink, width=3)
    ty = y + 17
    for l in lines:
        d.text((x + 22, ty), l, font=f, fill=ink)
        ty += int(size * 1.34)
    # stepped tail as one polygon, so it stays in the pixel language and reads
    # as a shape rather than three floating dashes
    s, b = 11, y + h
    bx = x + 34 if tail == "left" else x + w - 34 - 3 * s
    pts = [(bx, b), (bx + 3 * s, b)]
    for i in range(3):                       # descending staircase on one side
        pts += [(bx + (3 - i) * s, b + (i + 1) * s),
                (bx + (2 - i) * s, b + (i + 1) * s)]
    d.polygon(pts, fill=fill)
    d.line(pts[1:] + [pts[0]], fill=ink, width=3, joint="curve")
    d.rectangle([bx + 2, b - 3, bx + 3 * s - 2, b + 2], fill=fill)  # open the join
    return h


def receipt(d, x, y, n, agree, w=13, h=46, gap=9, on=MINT, off=INK_SOFT):
    for i in range(n):
        bx = x + i * (w + gap)
        if i < agree:
            d.rectangle([bx, y, bx + w, y + h], fill=on)
        else:
            d.rectangle([bx, y, bx + w, y + h], outline=off, width=3)


def header(d, W, M, tone, dark=False):
    fg = CREAM if dark else INK
    sub = (168, 154, 137) if dark else INK_SOFT
    d.text((M, 74), "HEADLINNE", font=font(34, 800), fill=fg)
    d.text((W - M, 78), "WED 5 AUG", font=font(26, 600), fill=sub, anchor="ra")
    d.rectangle([M, 132, W - M, 136], fill=tone)


def footer(d, W, H, M, dark=False):
    d.rectangle([M, H - 132, W - M, H - 130], fill=(58, 48, 39) if dark else PAPER_DEEP)
    d.text((M, H - 108), "headlinne.com", font=font(26, 600),
           fill=(168, 154, 137) if dark else INK_SOFT)


# --------------------------------------------------------------------------- #
# Post card
# --------------------------------------------------------------------------- #
def card(pose, kicker, headline, n, agree, outlets, tone=TERRA, say=None):
    W, H, M = 1080, 1350, 84
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    header(d, W, M, tone)

    sp = P.render(P.SPRITES[pose], 15)
    im.paste(sp, (M - 30, 196), sp)
    if say:
        bubble(im, d, say, M + 350, 236, 560)

    d.text((M, 606), kicker.upper(), font=font(30, 700), fill=tone)
    block(d, headline, font(84, 800), M, 664, W - M * 2, 96, INK)

    ry = H - 322
    receipt(d, M, ry, n, agree)
    d.text((M, ry + 74), f"{agree} of {n} outlets agree", font=font(34, 700), fill=INK)
    d.text((M, ry + 122), outlets, font=font(28, 500), fill=INK_SOFT)
    footer(d, W, H, M)
    return im


# --------------------------------------------------------------------------- #
# Carousel - five slides, five different jobs
# --------------------------------------------------------------------------- #
def slide_cover():
    W, H, M = 1080, 1350, 84
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    header(d, W, M, CORAL)
    sp = P.render(P.SPRITES["alert"], 16)
    im.paste(sp, (M - 34, 210), sp)
    bubble(im, d, "Something hit the Moon.", M + 400, 262, 540)
    d.text((M, 640), "SPACE", font=font(30, 700), fill=CORAL)
    block(d, "A SpaceX rocket just hit the Moon",
          font(92, 800), M, 698, W - M * 2, 104, INK)
    d.text((M, 918), "8,700 km/h. Nobody meant to do it.",
           font=font(42, 500), fill=INK_SOFT)
    receipt(d, M, H - 300, 8, 8)
    d.text((M, H - 226), "8 of 8 outlets agree", font=font(32, 700), fill=INK)
    footer(d, W, H, M)
    return im


def slide_scale():
    W, H, M = 1080, 1350, 84
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    header(d, W, M, TERRA)
    d.text((M, 220), "HOW BIG", font=font(30, 700), fill=TERRA)
    d.text((M, 274), "4", font=font(280, 800), fill=INK)
    d.text((M + 300, 420), "tonnes", font=font(64, 700), fill=INK)
    block(d, "About the size of a school bus, travelling at roughly six times "
             "the speed of a rifle bullet.", font(46, 500), M, 620, W - M * 2, 60, INK_SOFT)
    sp = P.render(P.SPRITES["read"], 12)
    im.paste(sp, (W - M - 320, H - 560), sp)
    bubble(im, d, "It left a crater. NASA photographed it.", M, H - 480, 520, tail="left")
    footer(d, W, H, M)
    return im


def slide_twist():
    W, H, M = 1080, 1350, 84
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    header(d, W, M, MARIGOLD)
    sp = P.render(P.SPRITES["puzzled"], 15)
    im.paste(sp, (M - 30, 200), sp)
    bubble(im, d, "Here's the bit I love.", M + 380, 250, 520)
    d.text((M, 610), "THIS HAPPENED ONCE BEFORE", font=font(30, 700), fill=MARIGOLD)
    block(d, "In 2022 everyone blamed SpaceX. It was a Chinese rocket.",
          font(78, 800), M, 668, W - M * 2, 92, INK)
    block(d, "The correction took months. The original headline is still "
             "the one most people remember.",
          font(38, 500), M, H - 400, W - M * 2, 52, INK_SOFT)
    footer(d, W, H, M)
    return im


def slide_close():
    W, H, M = 1080, 1350, 84
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    header(d, W, M, MINT)
    sp = P.render(P.SPRITES["verified"], 16)
    im.paste(sp, (M - 34, 210), sp)
    bubble(im, d, "I read all eight. They agree.", M + 400, 262, 520)
    d.text((M, 660), "SOURCES", font=font(30, 700), fill=MINT)
    receipt(d, M, 720, 8, 8)
    d.text((M, 800), "Al Jazeera · Space.com · Reuters +5", font=font(34, 600), fill=INK)
    block(d, "Headlinne reads every outlet covering a story and shows you where "
             "they agree — and where they don't.",
          font(40, 500), M, 900, W - M * 2, 54, INK_SOFT)
    footer(d, W, H, M)
    return im


# --------------------------------------------------------------------------- #
# Reel frames - 1080x1920, everything inside the safe zone
# --------------------------------------------------------------------------- #
def reel(pose, line, tone, say=None, counter=None, dark=True):
    W, H, M = 1080, 1920, 84
    im = Image.new("RGB", (W, H), NIGHT if dark else PAPER)
    d = ImageDraw.Draw(im)
    fg = CREAM if dark else INK
    header(d, W, M, tone, dark=dark)

    sp = P.render(P.SPRITES[pose], 17)
    im.paste(sp, (M - 36, 380), sp)
    if say:
        bubble(im, d, say, M + 430, 430, 500)

    if counter:
        d.text((M, 900), counter, font=font(190, 800), fill=tone)
        block(d, line, font(58, 600), M, 1140, W - M * 2, 74, fg)
    else:
        block(d, line, font(74, 800), M, 950, W - M * 2, 88, fg)

    # nothing may render below y=1450 - Instagram's UI owns it
    d.rectangle([M, 1400, W - M, 1404], fill=(58, 48, 39) if dark else PAPER_DEEP)
    d.text((M, 1424), "SAFE ZONE ENDS 1450", font=font(20, 600),
           fill=(96, 84, 72) if dark else (176, 164, 150))
    return im


def slide_cta():
    """Last slide of every carousel. Pip asks; the domain is the loudest thing."""
    W, H, M = 1080, 1350, 84
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    header(d, W, M, TERRA)
    sp = P.render(P.SPRITES["carry"], 16)
    im.paste(sp, (M - 34, 236), sp)
    bubble(im, d, "Come and read it.", M + 400, 288, 520)
    d.text((M, 700), "READ THE FULL STORY", font=font(30, 700), fill=TERRA)
    block(d, "headlinne.com", font(104, 800), M, 754, W - M * 2, 116, INK)
    block(d, "Every source on this story, side by side. Free to read, no account "
             "needed.", font(40, 500), M, 908, W - M * 2, 54, INK_SOFT)
    receipt(d, M, H - 300, 8, 8)
    d.text((M, H - 226), "8 of 8 outlets agree", font=font(32, 700), fill=INK)
    footer(d, W, H, M)
    return im


CARDS = {
    "moon": dict(pose="alert", kicker="Space", tone=CORAL,
                 headline="A SpaceX rocket just hit the Moon",
                 n=8, agree=8, outlets="Al Jazeera · Space.com · Reuters +5",
                 say="Something hit the Moon."),
}

if __name__ == "__main__":
    out = pathlib.Path(".")
    jobs = {
        "card_moon":  CARDS["moon"] and card(**CARDS["moon"]),
        "car_cover":  slide_cover(),
        "car_scale":  slide_scale(),
        "car_twist":  slide_twist(),
        "car_close":  slide_close(),
        "car_cta":    slide_cta(),
        "reel_hook":  reel("alert", "A four-tonne rocket stage just hit the Moon.",
                           CORAL, say="No one meant to do this."),
        "reel_count": reel("idle", "kilometres per hour at impact. Roughly three "
                           "tonnes of TNT.", MARIGOLD, counter="8,700"),
        "reel_twist": reel("puzzled", "Last time this happened everyone blamed "
                           "SpaceX. It was a Chinese rocket.", MARIGOLD,
                           say="Worth remembering."),
    }
    for name, im in jobs.items():
        im.save(out / f"{name}.png")
        th = im.copy(); th.thumbnail((330, 520), Image.LANCZOS)
        b = io.BytesIO(); th.save(b, "JPEG", quality=84, optimize=True)
        (out / f"fb64_{name}.b64").write_text(base64.b64encode(b.getvalue()).decode())

    # review sheets
    for tag, keys in (("carousel", ["car_cover", "car_scale", "car_twist", "car_close"]),
                      ("reels", ["reel_hook", "reel_count", "reel_twist"])):
        ts = []
        for k in keys:
            t = jobs[k].copy(); t.thumbnail((250, 420), Image.LANCZOS); ts.append(t)
        g = 16
        sh = Image.new("RGB", (len(ts) * (max(t.width for t in ts) + g) + g,
                               max(t.height for t in ts) + g * 2), (20, 16, 32))
        for i, t in enumerate(ts):
            sh.paste(t, (g + i * (max(x.width for x in ts) + g), g))
        sh.save(out / f"sheet_{tag}.png")
    print("rendered:", ", ".join(jobs))
