"""Paper-ground reel with kinetic variable-weight type and Pip walking along.

Markup in a line: *word* renders at weight 800 in the accent colour and a touch
larger. Everything else sits at 450. That is the variable font doing editorial
work - the emphasis is on the word that carries the fact, not the whole line.
"""
import base64, io, pathlib
import re
from PIL import Image, ImageDraw, ImageFont
import pip as P

FONTS = pathlib.Path("C:/Users/khand/Downloads/socials/assets/fonts")
W, H, M = 1080, 1920, 84
SAFE_TOP, SAFE_BOT = 180, 1450

PAPER, PAPER_DEEP = (247, 241, 230), (231, 220, 202)
INK, INK_SOFT = (25, 19, 16), (110, 97, 86)
TERRA, MINT, MARIGOLD, CORAL = (196, 86, 47), (30, 107, 84), (148, 98, 23), (206, 62, 34)

_cache = {}


def font(px, weight=800):
    key = (px, weight)
    if key not in _cache:
        f = ImageFont.truetype(str(FONTS / "Manrope-Variable.ttf"), px)
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
        _cache[key] = f
    return _cache[key]


def tokens(text):
    """Split into (word, is_hero). *starred spans* may cover several words, and
    punctuation immediately after a span stays glued to the last hero word."""
    out = []
    for part in re.split(r"(\*[^*]+\*)", text):
        if not part:
            continue
        hero = part.startswith("*") and part.endswith("*") and len(part) > 2
        body = part[1:-1] if hero else part
        if not hero and out:
            # punctuation sitting flush against a closing * belongs to that word
            m = re.match(r"^([,.;:!?)\]—]+)", body)
            if m:
                out[-1][0] += m.group(1)
                body = body[m.end():]
        for w in body.split():
            out.append([w, hero])
    return [(w, h) for w, h in out]


def rich(d, text, x, y, max_w, size, accent, base_w=450, hero_w=800, lh=1.16):
    """Lay out a line where *starred* spans get the heavy variable weight."""
    lines, cur, curw = [], [], 0
    space = d.textlength(" ", font=font(size, base_w))
    for w, hero in tokens(text):
        f = font(int(size * 1.08), hero_w) if hero else font(size, base_w)
        tw = d.textlength(w, font=f)
        if curw + tw > max_w and cur:
            lines.append(cur); cur, curw = [], 0
        cur.append((w, hero, f, tw)); curw += tw + space
    if cur:
        lines.append(cur)

    for ln in lines:
        cx = x
        for w, hero, f, tw in ln:
            d.text((cx, y), w, font=f, fill=accent if hero else INK)
            cx += tw + space
        y += int(size * lh)
    return y


def frame(pip_frame, line, accent, walk_x=0, bubble=None, counter=None,
          ticks=None):
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)

    d.text((M, 74), "HEADLINNE", font=font(34, 800), fill=INK)
    d.text((W - M, 78), "WED 5 AUG", font=font(26, 600), fill=INK_SOFT, anchor="ra")
    d.rectangle([M, 132, W - M, 136], fill=accent)

    # ground line Pip walks along - Mario needs a floor
    gy = 800
    d.rectangle([0, gy, W, gy + 5], fill=PAPER_DEEP)

    sp = P.render(pip_frame, 14)
    im.paste(sp, (M - 40 + walk_x, gy - sp.height + 4), sp)

    if bubble:
        bx, by = M + 300 + walk_x, gy - 420
        f = font(36, 650)
        tw = d.textlength(bubble, font=f)
        bw, bh = int(tw) + 48, 92
        d.rectangle([bx, by, bx + bw, by + bh], fill=(255, 253, 248))
        d.rectangle([bx, by, bx + bw, by + bh], outline=INK, width=4)
        d.text((bx + 24, by + 22), bubble, font=f, fill=INK)
        s = 12
        pts = [(bx + 30, by + bh), (bx + 30 + 3 * s, by + bh)]
        for i in range(3):
            pts += [(bx + 30 + (3 - i) * s, by + bh + (i + 1) * s),
                    (bx + 30 + (2 - i) * s, by + bh + (i + 1) * s)]
        d.polygon(pts, fill=(255, 253, 248))
        d.line(pts[1:] + [pts[0]], fill=INK, width=4, joint="curve")
        d.rectangle([bx + 32, by + bh - 4, bx + 30 + 3 * s - 2, by + bh + 3],
                    fill=(255, 253, 248))

    y = 880
    if counter:
        d.text((M, y), counter, font=font(200, 800), fill=accent)
        y += 250
    rich(d, line, M, y, W - M * 2, 76, accent)

    if ticks:
        n, agree = ticks
        ty = 1300
        for i in range(n):
            bx = M + i * 22
            if i < agree:
                d.rectangle([bx, ty, bx + 13, ty + 46], fill=MINT)
            else:
                d.rectangle([bx, ty, bx + 13, ty + 46], outline=INK_SOFT, width=3)

    d.rectangle([M, SAFE_BOT - 46, W - M, SAFE_BOT - 43], fill=PAPER_DEEP)
    d.text((M, SAFE_BOT - 32), "SAFE ZONE ENDS 1450", font=font(20, 600),
           fill=(186, 174, 158))
    return im


# --------------------------------------------------------------------------- #
# The script. Pip narrates. ~14 beats in 15s.
# --------------------------------------------------------------------------- #
WALK = P.walk_cycle()
TALK = P.talk_cycle()

SCRIPT = [
    # (seconds, pip frame, line, accent, walk offset, bubble, counter, ticks)
    (0.0, WALK[0], "Okay. Something *hit the Moon*.", CORAL, 0, "Right—", None, None),
    (1.3, WALK[1], "Nobody *meant* to do it.", CORAL, 40, None, None, None),
    (2.4, WALK[2], "It was *four tonnes*. A school bus.", TERRA, 80, None, None, None),
    (3.8, TALK[1], "It was going", MARIGOLD, 120, None, "8,700", None),
    (5.2, WALK[0], "*Six times* the speed of a rifle bullet.", MARIGOLD, 160, "Genuinely.", None, None),
    (6.7, WALK[1], "It left a *crater* near Einstein.", TERRA, 200, None, None, None),
    (8.1, WALK[2], "*Two orbiters* turned to photograph it.", TERRA, 240, None, None, None),
    (9.5, TALK[1], "Here's my *favourite* part.", MARIGOLD, 280, "Wait.", None, None),
    (10.9, WALK[0], "This happened *once before*.", MARIGOLD, 320, None, None, None),
    (12.1, WALK[1], "Everyone blamed *SpaceX*.", CORAL, 360, None, None, None),
    (13.3, WALK[2], "It was a *Chinese* rocket.", CORAL, 400, "Oh.", None, None),
    (14.6, TALK[1], "The correction took *months*.", INK_SOFT, 440, None, None, None),
    (16.0, WALK[0], "I read all *eight* write-ups.", MINT, 480, None, None, (8, 8)),
    (17.4, WALK[1], "This time they *agree*.", MINT, 520, "Good.", None, (8, 8)),
]


def wpm():
    words = sum(len(s[2].replace("*", "").split()) for s in SCRIPT)
    dur = SCRIPT[-1][0] + 1.4
    return words, dur, round(words / (dur / 60))


if __name__ == "__main__":
    out = pathlib.Path(".")
    frames = []
    for i, (t, pf, line, acc, wx, bub, cnt, tk) in enumerate(SCRIPT):
        im = frame(pf, line, acc, walk_x=wx, bubble=bub, counter=cnt, ticks=tk)
        frames.append(im)
        if i in (0, 3, 10, 13):
            im.save(out / f"rl_{i:02d}.png")
            th = im.copy(); th.thumbnail((330, 560), Image.LANCZOS)
            b = io.BytesIO(); th.save(b, "JPEG", quality=85, optimize=True)
            (out / f"rb64_{i:02d}.b64").write_text(base64.b64encode(b.getvalue()).decode())

    # animated preview: every beat, plus the walk cycle between them
    anim = [f.copy() for f in frames]
    for a in anim:
        a.thumbnail((300, 534), Image.LANCZOS)
    anim[0].save(out / "reel_preview.gif", save_all=True,
                 append_images=anim[1:], duration=1100, loop=0, optimize=True)
    with open(out / "reel_preview.gif", "rb") as fh:
        (out / "gif_reel.b64").write_text(base64.b64encode(fh.read()).decode())

    # Pip walking, on paper, for the character section
    P.gif(P.walk_cycle(), out / "pip_walk.gif", scale=9, ms=140, bg=PAPER)
    with open(out / "pip_walk.gif", "rb") as fh:
        (out / "gif_walk.b64").write_text(base64.b64encode(fh.read()).decode())

    w, dur, rate = wpm()
    print(f"{len(SCRIPT)} beats · {w} words · {dur}s · {rate} wpm")
    sheet = [f.copy() for f in frames[:4]]
    for s in sheet:
        s.thumbnail((250, 445), Image.LANCZOS)
    g = 14
    sh = Image.new("RGB", (len(sheet) * (sheet[0].width + g) + g,
                           sheet[0].height + g * 2), (231, 220, 202))
    for i, s in enumerate(sheet):
        sh.paste(s, (g + i * (sheet[0].width + g), g))
    sh.save(out / "sheet_reel_paper.png")
