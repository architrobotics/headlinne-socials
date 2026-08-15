"""X cards - 1200x675 (16:9). On X the post text is the hook and the image is
the evidence, so the card never repeats the headline. It carries the proof.

Three card types, matching the three things only your pipeline can say:
  receipt   - who reported it and whether they agree
  compare   - two outlets, two numbers, same document
  correct   - what was reported vs what turned out to be true
"""
import base64, io, pathlib
from PIL import Image, ImageDraw, ImageFont
import pip as P
import plate as PL

FONTS = pathlib.Path("C:/Users/khand/Downloads/socials/assets/fonts")
W, H, M = 1200, 675, 56
PAPER, PAPER_DEEP = (247, 241, 230), (231, 220, 202)
INK, INK_SOFT = (25, 19, 16), (110, 97, 86)
TERRA, MINT, MARIGOLD, CORAL = (196, 86, 47), (30, 107, 84), (148, 98, 23), (206, 62, 34)
_c = {}


def font(px, weight=800):
    k = (px, weight)
    if k not in _c:
        f = ImageFont.truetype(str(FONTS / "Manrope-Variable.ttf"), px)
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
        _c[k] = f
    return _c[k]


def wrap(d, text, fnt, mw):
    out, cur = [], ""
    for w in text.split():
        t = f"{cur} {w}".strip()
        if d.textlength(t, font=fnt) <= mw:
            cur = t
        else:
            out.append(cur); cur = w
    if cur:
        out.append(cur)
    return out


def chrome(d, tone, label):
    d.text((M, 40), "HEADLINNE", font=font(28, 800), fill=INK)
    d.text((W - M, 42), label.upper(), font=font(20, 700), fill=tone, anchor="ra")
    d.rectangle([M, 84, W - M, 87], fill=tone)
    d.text((M, H - 46), "headlinne.com", font=font(20, 600), fill=INK_SOFT)


def receipt_card():
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    chrome(d, MINT, "Sources")
    d.text((M, 132), "8 of 8 outlets agree", font=font(66, 800), fill=INK)
    ticks = ["Reuters", "AP", "Al Jazeera", "Space.com", "New Scientist",
             "Sky", "The Verge", "Guardian"]
    y = 236
    for i, name in enumerate(ticks):
        col = i % 2
        row = i // 2
        x = M + col * 480
        yy = y + row * 62
        d.rectangle([x, yy, x + 13, yy + 40], fill=MINT)
        d.text((x + 30, yy + 2), name, font=font(30, 600), fill=INK)
    sp = P.render(P.SPRITES["verified"], 8)
    im.paste(sp, (W - M - sp.width, H - 60 - sp.height), sp)
    return im


def compare_card():
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    chrome(d, MARIGOLD, "Sources disagree")
    d.text((M, 128), "Same memo. Two numbers.", font=font(52, 800), fill=INK)
    for i, (who, num, n) in enumerate((("Reuters", "12,000", 3),
                                       ("Financial Times", "4,000", 4))):
        x = M + i * 560
        d.rectangle([x, 214, x + 500, 470], fill=(255, 253, 248))
        d.rectangle([x, 214, x + 500, 470], outline=INK, width=4)
        d.text((x + 26, 238), who.upper(), font=font(22, 700), fill=MARIGOLD)
        d.text((x + 26, 276), num, font=font(96, 800), fill=INK)
        d.text((x + 26, 392), "jobs affected", font=font(26, 500), fill=INK_SOFT)
    d.text((M, 506), "One counted contractors. One didn't.",
           font=font(30, 600), fill=INK_SOFT)
    sp = P.render(P.SPRITES["puzzled"], 8)
    im.paste(sp, (W - M - sp.width, H - 52 - sp.height), sp)
    return im


def correct_card():
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    chrome(d, CORAL, "Correction")
    rows = [("REPORTED 2022", "A SpaceX Falcon 9 upper stage", CORAL, True),
            ("ESTABLISHED LATER", "A Chinese Long March 3C, launched 2014", MINT, False)]
    y = 148
    for label, text, col, struck in rows:
        d.text((M, y), label, font=font(22, 700), fill=col)
        f = font(46, 750)
        d.text((M, y + 38), text, font=f, fill=INK if not struck else INK_SOFT)
        if struck:
            tw = d.textlength(text, font=f)
            d.rectangle([M, y + 62, M + tw, y + 66], fill=CORAL)
        y += 176
    d.text((M, 524), "The correction took months.", font=font(26, 500), fill=INK_SOFT)
    sp = P.render(P.SPRITES["read"], 8)
    im.paste(sp, (W - M - sp.width, H - 52 - sp.height), sp)
    return im


def photo_card():
    """When the story has an image, the card is the image plus one fact."""
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    chrome(d, TERRA, "Space")
    pl = PL.tilted(PL.moon_scene(w=460, h=300), angle=-3.0,
                   caption="ILLUSTRATION · NOT A PHOTOGRAPH", font=font(18, 600))
    pl.thumbnail((520, 420), Image.LANCZOS)
    im.paste(pl, (W - M - pl.width, 122), pl)
    d.text((M, 150), "8,700", font=font(110, 800), fill=TERRA)
    d.text((M, 282), "km/h at impact", font=font(34, 600), fill=INK)
    for i, l in enumerate(wrap(d, "Four tonnes, roughly the size of a school bus.",
                               font(28, 450), 520)):
        d.text((M, 350 + i * 38), l, font=font(28, 450), fill=INK_SOFT)
    sp = P.render(P.SPRITES["idle"], 7)
    im.paste(sp, (M, H - 52 - sp.height), sp)
    return im


def cta_card():
    """The reply that closes every X thread."""
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    chrome(d, TERRA, "Read it")
    d.text((M, 138), "headlinne.com", font=font(88, 800), fill=INK)
    d.text((M, 254), "Every source on this story, side by side.",
           font=font(34, 500), fill=INK_SOFT)
    d.text((M, 306), "Free to read. No account needed.",
           font=font(34, 500), fill=INK_SOFT)
    for i in range(8):
        bx = M + i * 22
        d.rectangle([bx, 396, bx + 13, 438], fill=MINT)
    d.text((M + 200, 400), "8 of 8 outlets agree", font=font(30, 700), fill=INK)
    sp = P.render(P.SPRITES["carry"], 9)
    im.paste(sp, (W - M - sp.width, H - 66 - sp.height), sp)
    return im


CARDS = {"x_cta": cta_card, "x_receipt": receipt_card, "x_compare": compare_card,
         "x_correct": correct_card, "x_photo": photo_card}

if __name__ == "__main__":
    out = pathlib.Path(".")
    tiles = []
    for name, fn in CARDS.items():
        im = fn()
        im.save(out / f"{name}.png")
        th = im.copy(); th.thumbnail((520, 300), Image.LANCZOS)
        b = io.BytesIO(); th.save(b, "JPEG", quality=86, optimize=True)
        (out / f"xb64_{name}.b64").write_text(base64.b64encode(b.getvalue()).decode())
        t = im.copy(); t.thumbnail((330, 190), Image.LANCZOS); tiles.append(t)
    g = 14
    sh = Image.new("RGB", (2 * (tiles[0].width + g) + g,
                           2 * (tiles[0].height + g) + g), PAPER_DEEP)
    for i, t in enumerate(tiles):
        sh.paste(t, (g + (i % 2) * (t.width + g), g + (i // 2) * (t.height + g)))
    sh.save(out / "sheet_x.png")
    print("x cards:", ", ".join(CARDS))
