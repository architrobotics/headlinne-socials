"""Mock up the redesigned Headlinne post card. Simple, clean, Pip does the work."""
import base64, io, pathlib
from PIL import Image, ImageDraw, ImageFont
import pip as P

FONTS = pathlib.Path("C:/Users/khand/Downloads/socials/assets/fonts")
Wc, Hc = 1080, 1350

PAPER      = (247, 241, 230)
PAPER_DEEP = (233, 223, 206)
INK        = (25, 19, 16)
INK_SOFT   = (110, 97, 86)
TERRA      = (196, 86, 47)
MINT       = (30, 107, 84)
MARIGOLD   = (255, 180, 61)
CORAL      = (232, 74, 42)


def font(px, weight=800):
    f = ImageFont.truetype(str(FONTS / "Manrope-Variable.ttf"), px)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f


def wrap(draw, text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if draw.textlength(t, font=fnt) <= max_w:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def receipt(draw, x, y, n, agree, w=13, h=46, gap=9):
    """The source strip: one tick per outlet, filled where corroborated."""
    for i in range(n):
        bx = x + i * (w + gap)
        if i < agree:
            draw.rectangle([bx, y, bx + w, y + h], fill=MINT)
        else:
            draw.rectangle([bx, y, bx + w, y + h], outline=INK_SOFT, width=3)


def card(pose, kicker, headline, sources, agree, outlets, tone=TERRA):
    im = Image.new("RGB", (Wc, Hc), PAPER)
    d = ImageDraw.Draw(im)
    M = 84

    # header: wordmark left, date right. one hairline, no pills.
    d.text((M, 74), "HEADLINNE", font=font(34, 800), fill=INK)
    d.text((Wc - M, 78), "TUE 15 AUG", font=font(26, 600), fill=INK_SOFT, anchor="ra")
    d.rectangle([M, 132, Wc - M, 136], fill=tone)

    # Pip, always the same size, always the same place
    sprite = P.render(P.SPRITES[pose], 15)
    im.paste(sprite, (M - 30, 196), sprite)

    # kicker
    d.text((M, 606), kicker.upper(), font=font(30, 700), fill=tone)

    # headline
    f = font(84, 800)
    lines = wrap(d, headline, f, Wc - M * 2)
    y = 664
    for ln in lines:
        d.text((M, y), ln, font=f, fill=INK)
        y += 96

    # the receipt strip does the arguing
    ry = Hc - 322
    receipt(d, M, ry, sources, agree)
    d.text((M, ry + 74), f"{agree} of {sources} outlets agree",
           font=font(34, 700), fill=INK)
    d.text((M, ry + 122), outlets, font=font(28, 500), fill=INK_SOFT)

    d.rectangle([M, Hc - 132, Wc - M, Hc - 130], fill=PAPER_DEEP)
    d.text((M, Hc - 108), "headlinne.com", font=font(26, 600), fill=INK_SOFT)
    return im


CARDS = {
    "brief": dict(
        pose="carry", kicker="Your brief",
        headline="The Bank held rates for a fourth time",
        sources=9, agree=9, outlets="Reuters · FT · Bloomberg +6"),
    "breaking": dict(
        pose="alert", kicker="Developing",
        headline="A cloud outage briefly took down a dozen banking apps",
        sources=6, agree=4, outlets="The Verge · AP · Sky +3", tone=CORAL),
    "disagree": dict(
        pose="puzzled", kicker="Sources disagree",
        headline="Two outlets read the same memo and got numbers 8,000 apart",
        sources=7, agree=3, outlets="Reuters · FT · WSJ +4", tone=MARIGOLD),
}

if __name__ == "__main__":
    out = pathlib.Path(".")
    tiles = []
    for name, kw in CARDS.items():
        im = card(**kw)
        im.save(out / f"card_{name}.png")
        th = im.copy(); th.thumbnail((300, 400), Image.LANCZOS)
        b = io.BytesIO(); th.save(b, "JPEG", quality=82, optimize=True)
        (out / f"cardb64_{name}.b64").write_text(base64.b64encode(b.getvalue()).decode())
        t = im.copy(); t.thumbnail((240, 320), Image.LANCZOS); tiles.append(t)
    gap = 18
    sheet = Image.new("RGB", (len(tiles) * (tiles[0].width + gap) + gap,
                              tiles[0].height + gap * 2), (20, 16, 32))
    for i, t in enumerate(tiles):
        sheet.paste(t, (gap + i * (t.width + gap), gap))
    sheet.save(out / "card_sheet.png")
    print("cards:", ", ".join(CARDS))
