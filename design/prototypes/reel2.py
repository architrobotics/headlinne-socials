"""Reel v2 - informational register, image plates, and Pip doing more than walk.

Voice note: Pip explains, he does not react. "On Tuesday a four-tonne stage
struck the Moon" rather than "Okay. Something hit the Moon." Educational, warm,
never chatty. The interest lives in the facts, not in the delivery.
"""
import base64, io, pathlib, re
from PIL import Image, ImageDraw, ImageFont
import pip as P
import plate as PL

FONTS = pathlib.Path("C:/Users/khand/Downloads/socials/assets/fonts")
W, H, M = 1080, 1920, 84
SAFE_BOT = 1450
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


def tokens(text):
    out = []
    for part in re.split(r"(\*[^*]+\*)", text):
        if not part:
            continue
        hero = part.startswith("*") and part.endswith("*") and len(part) > 2
        body = part[1:-1] if hero else part
        if not hero and out:
            m = re.match(r"^([,.;:!?)\]—]+)", body)
            if m:
                out[-1][0] += m.group(1); body = body[m.end():]
        for w in body.split():
            out.append([w, hero])
    return [(w, h) for w, h in out]


def rich(d, text, x, y, max_w, size, accent, base_w=450, hero_w=800):
    lines, cur, curw = [], [], 0
    sp = d.textlength(" ", font=font(size, base_w))
    for w, hero in tokens(text):
        f = font(int(size * 1.08), hero_w) if hero else font(size, base_w)
        tw = d.textlength(w, font=f)
        if curw + tw > max_w and cur:
            lines.append(cur); cur, curw = [], 0
        cur.append((w, hero, f, tw)); curw += tw + sp
    if cur:
        lines.append(cur)
    for ln in lines:
        cx = x
        for w, hero, f, tw in ln:
            d.text((cx, y), w, font=f, fill=accent if hero else INK)
            cx += tw + sp
        y += int(size * 1.16)
    return y


def bubble(d, text, x, y):
    f = font(34, 650)
    tw = d.textlength(text, font=f)
    bw, bh = int(tw) + 44, 86
    d.rectangle([x, y, x + bw, y + bh], fill=(255, 253, 248))
    d.rectangle([x, y, x + bw, y + bh], outline=INK, width=4)
    d.text((x + 22, y + 20), text, font=f, fill=INK)
    s = 11
    pts = [(x + 28, y + bh), (x + 28 + 3 * s, y + bh)]
    for i in range(3):
        pts += [(x + 28 + (3 - i) * s, y + bh + (i + 1) * s),
                (x + 28 + (2 - i) * s, y + bh + (i + 1) * s)]
    d.polygon(pts, fill=(255, 253, 248))
    d.line(pts[1:] + [pts[0]], fill=INK, width=4, joint="curve")
    d.rectangle([x + 30, y + bh - 4, x + 28 + 3 * s - 2, y + bh + 3],
                fill=(255, 253, 248))


def frame(pose_frame, line, accent, x=0, say=None, counter=None, plate=None,
          plate_angle=-3.4, plate_cap=None, ticks=None):
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    d.text((M, 74), "HEADLINNE", font=font(34, 800), fill=INK)
    d.text((W - M, 78), "WED 5 AUG", font=font(26, 600), fill=INK_SOFT, anchor="ra")
    d.rectangle([M, 132, W - M, 136], fill=accent)

    if plate is not None:
        pl = PL.tilted(plate, angle=plate_angle, caption=plate_cap,
                       font=font(22, 600))
        pl.thumbnail((W - M * 2 + 40, 620), Image.LANCZOS)
        im.paste(pl, ((W - pl.width) // 2, 210), pl)
        gy = 980
    else:
        gy = 820

    d.rectangle([0, gy, W, gy + 5], fill=PAPER_DEEP)
    sp = P.render(pose_frame, 13)
    im.paste(sp, (M - 36 + x, gy - sp.height + 4), sp)
    if say:
        bubble(d, say, M + 300 + x, gy - sp.height - 96)

    y = gy + 70
    if counter:
        d.text((M, y), counter, font=font(170, 800), fill=accent)
        y += 214
    rich(d, line, M, y, W - M * 2, 62, accent)

    if ticks:
        n, agree = ticks
        for i in range(n):
            bx = M + i * 22
            if i < agree:
                d.rectangle([bx, 1340, bx + 13, 1386], fill=MINT)
            else:
                d.rectangle([bx, 1340, bx + 13, 1386], outline=INK_SOFT, width=3)

    d.rectangle([M, SAFE_BOT - 44, W - M, SAFE_BOT - 41], fill=PAPER_DEEP)
    d.text((M, SAFE_BOT - 30), "SAFE ZONE ENDS 1450", font=font(20, 600),
           fill=(186, 174, 158))
    return im


WALK, TALK = P.walk_cycle(), P.talk_cycle()
JUMP, POINT, PRESENT = P.jump_cycle(), P.point_cycle(), P.present_cycle()
MOON = PL.moon_scene()
CRATER = PL.moon_scene(seed=11)

SCRIPT = [
    (0.0,  WALK[0],    "On Tuesday a *four-tonne* rocket stage struck the Moon.", CORAL, 0, None, None, None, None),
    (1.9,  WALK[1],    "It was the second stage of a *Falcon 9*.", CORAL, 40, None, None, None, None),
    (3.7,  POINT[0],   "Solar activity pulled it *off course*.", TERRA, 80, "Not deliberate.", None, None, None),
    (5.5,  PRESENT[0], "It hit near *Einstein Crater*.", TERRA, 120, None, None, MOON, "ILLUSTRATION · NOT A PHOTOGRAPH"),
    (7.3,  JUMP[2],    "kilometres per hour.", MARIGOLD, 150, None, "8,700", None, None),
    (9.1,  WALK[2],    "*Six times* the speed of a rifle bullet.", MARIGOLD, 190, None, None, None, None),
    (11.0, TALK[1],    "Energy equal to *three tonnes of TNT*.", MARIGOLD, 230, None, None, None, None),
    (12.9, POINT[1],   "*Two orbiters* turned to photograph the site.", TERRA, 270, None, None, CRATER, "ILLUSTRATION · NOT A PHOTOGRAPH"),
    (14.8, WALK[0],    "NASA's *LRO*, and South Korea's *Danuri*.", TERRA, 310, None, None, None, None),
    (16.6, PRESENT[1], "This has happened *once before*.", MARIGOLD, 350, None, None, None, None),
    (18.3, WALK[1],    "In 2022 a stage left a *double crater*.", MARIGOLD, 390, None, None, None, None),
    (20.1, TALK[1],    "It was reported as *SpaceX*.", CORAL, 430, None, None, None, None),
    (21.8, POINT[0],   "It was a Chinese *Long March 3C*.", CORAL, 470, "Corrected later.", None, None, None),
    (23.6, WALK[2],    "The correction took *months*.", INK_SOFT, 510, None, None, None, None),
    (25.4, PRESENT[0], "*Eight* outlets covered this. All eight agree.", MINT, 550, None, None, None, None),
]


def wpm():
    words = sum(len(re.sub(r"\*", "", b[2]).split()) for b in SCRIPT)
    dur = SCRIPT[-1][0] + 1.6
    return words, round(dur, 1), round(words / (dur / 60))


if __name__ == "__main__":
    out = pathlib.Path(".")
    frames = []
    for i, (t, pf, line, acc, x, say, cnt, pl, cap) in enumerate(SCRIPT):
        tk = (8, 8) if i >= 14 else None
        im = frame(pf, line, acc, x=x, say=say, counter=cnt, plate=pl,
                   plate_angle=-3.4 if i % 2 == 0 else 2.8,
                   plate_cap=cap, ticks=tk)
        frames.append(im)
        if i in (0, 3, 4, 7, 12, 14):
            im.save(out / f"r2_{i:02d}.png")
            th = im.copy(); th.thumbnail((330, 560), Image.LANCZOS)
            b = io.BytesIO(); th.save(b, "JPEG", quality=85, optimize=True)
            (out / f"r2b64_{i:02d}.b64").write_text(base64.b64encode(b.getvalue()).decode())

    anim = [f.copy() for f in frames]
    for a in anim:
        a.thumbnail((296, 526), Image.LANCZOS)
    anim[0].save(out / "reel2.gif", save_all=True, append_images=anim[1:],
                 duration=1150, loop=0, optimize=True)
    (out / "gif_reel2.b64").write_text(
        base64.b64encode((out / "reel2.gif").read_bytes()).decode())

    P.gif(P.jump_cycle(), out / "pip_jump.gif", scale=8, ms=130, bg=PAPER)
    (out / "gif_jump.b64").write_text(
        base64.b64encode((out / "pip_jump.gif").read_bytes()).decode())

    sheet = [frames[i].copy() for i in (0, 3, 4, 7)]
    for s in sheet:
        s.thumbnail((250, 445), Image.LANCZOS)
    g = 14
    sh = Image.new("RGB", (len(sheet) * (sheet[0].width + g) + g,
                           sheet[0].height + g * 2), PAPER_DEEP)
    for i, s in enumerate(sheet):
        sh.paste(s, (g + i * (sheet[0].width + g), g))
    sh.save(out / "sheet_reel2.png")
    w, dur, rate = wpm()
    print(f"{len(SCRIPT)} beats · {w} words · {dur}s · {rate} wpm")
