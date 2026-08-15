"""A real reel draft: 24fps, word-by-word reveal, walking Pip, multiple tilted
photo plates, encoded to MP4.

Frame budget, 1080x1920 (rendered at half for the draft):
    0- 140  masthead + progress bar
  150- 200  chapter marker
  210- 830  plate zone - one to three photos, tilted, scattered
  830-1010  Pip on the ground line, bubble above
 1020-1210  the kinetic line
 1215-1300  secondary detail - the extra information
 1310-1400  persistent source strip
 1400-1450  safe-zone rule
 1450+      dead. Instagram's UI owns it.

Plates take any PIL image, so production drops real article photographs
straight in - news/images.py already resolves them via best_story_image().
The generated scenes here are only the fallback rung.
"""
import pathlib, re, subprocess, shutil, sys
from PIL import Image, ImageDraw, ImageFont
import pip as P
import plate as PL

SCALE = 0.5                      # draft resolution
W, H = int(1080 * SCALE), int(1920 * SCALE)
M = int(84 * SCALE)
FPS = 24
FONTS = pathlib.Path("C:/Users/khand/Downloads/socials/assets/fonts")

PAPER, DEEP = (247, 241, 230), (231, 220, 202)
INK, SOFT = (25, 19, 16), (110, 97, 86)
TERRA, MINT = (196, 86, 47), (30, 107, 84)
MARIGOLD, CORAL = (148, 98, 23), (206, 62, 34)
_f, _plates, _sprites = {}, {}, {}
TRACE = []          # (label, x0, y0, x1, y1) for every element drawn


def S(v):
    return int(v * SCALE)


def font(px, weight=800):
    k = (S(px), weight)
    if k not in _f:
        ft = ImageFont.truetype(str(FONTS / "Manrope-Variable.ttf"), max(8, k[0]))
        try:
            ft.set_variation_by_axes([weight])
        except Exception:
            pass
        _f[k] = ft
    return _f[k]


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


def note(label, x0, y0, x1, y1):
    TRACE.append((label, int(x0), int(y0), int(x1), int(y1)))


def rich(d, text, x, y, max_w, size, accent, reveal=1.0, base_w=450, hero_w=800,
         label="line"):
    toks = tokens(text)
    show = max(1, int(len(toks) * reveal + 0.999)) if reveal < 1 else len(toks)
    lines, cur, curw = [], [], 0
    sp = d.textlength(" ", font=font(size, base_w))
    for i, (w, hero) in enumerate(toks):
        f = font(int(size * 1.08), hero_w) if hero else font(size, base_w)
        tw = d.textlength(w, font=f)
        if curw + tw > max_w and cur:
            lines.append(cur); cur, curw = [], 0
        cur.append((w, hero, f, tw, i)); curw += tw + sp
    if cur:
        lines.append(cur)
    lh = int(S(size) * 1.16)
    top = y
    for ln in lines:
        cx = x
        for w, hero, f, tw, i in ln:
            if i < show:
                d.text((cx, y), w, font=f, fill=accent if hero else INK)
            cx += tw + sp
        y += lh
    if lines:
        note(label, x, top, x + max_w, y)
    return y


def get_plate(key, maker, angle, cap, maxw=520):
    ck = (key, maxw)
    if ck not in _plates:
        pl = PL.tilted(maker(), angle=angle, caption=cap, font=font(22, 600))
        pl.thumbnail((S(maxw), S(392)), Image.LANCZOS)
        _plates[ck] = pl
    return _plates[ck]


def sprite(grid, scale):
    k = (id(grid), scale)
    if k not in _sprites:
        _sprites[k] = P.render(grid, scale)
    return _sprites[k]


# --------------------------------------------------------------------------- #
WALK, TALK = P.walk_cycle(), P.talk_cycle()
JUMP, POINT, PRESENT = P.jump_cycle(), P.point_cycle(), P.present_cycle()

SOURCES = "Reuters · AP · Al Jazeera · Space.com · New Scientist +3"

# (start, chapter, pose_set, line, detail, accent, bubble, counter, plates)
BEATS = [
    (0.0, "What happened", WALK, "On Tuesday a *four-tonne* rocket stage struck the Moon.",
     "A Falcon 9 second stage.", CORAL, None, None, []),
    (2.6, "What happened", POINT, "It was up there because solar activity pulled it *off course*.",
     "Nobody planned this.", CORAL, "Not deliberate.", None, []),
    (5.4, "Where", PRESENT, "It came down near *Einstein Crater*, on the far side.",
     "Out of view from Earth.", TERRA, None, None, ["moon"]),
    (8.2, "How fast", JUMP, "kilometres per hour.",
     "Which is about six times a rifle bullet.", MARIGOLD, None, "8,700", []),
    (10.8, "How hard", TALK, "So it released energy equal to *three tonnes of TNT*.",
     "Small, as impacts go.", MARIGOLD, None, None, []),
    (13.6, "Who watched", POINT, "*Two orbiters* turned to photograph the site.",
     "NASA's LRO, and South Korea's Danuri.", TERRA, None, None, ["moon", "crater"]),
    (16.6, "The precedent", PRESENT, "And this has happened *once before*.",
     "March 2022, also the far side.", MARIGOLD, None, None, []),
    (19.2, "The correction", TALK, "That one was reported as *SpaceX* too.",
     "Every major outlet ran it.", CORAL, None, None, []),
    (21.8, "The correction", POINT, "It turned out to be a Chinese *Long March 3C*.",
     "Corrected months later.", CORAL, "Corrected later.", None, []),
    (24.6, "Sources", PRESENT, "*Eight* outlets covered this one, and all eight agree.",
     "We read every one of them.", MINT, None, None, []),
    (27.2, "Read it", None, "The full story is on *headlinne.com*.",
     "Every source, side by side.", TERRA, "Come and read it.", None, []),
]
DURATION = 30.0

PLATE_SPECS = {
    "moon":   (lambda: PL.moon_scene(w=520, h=350), -3.6, "ILLUSTRATION · NOT A PHOTOGRAPH"),
    "crater": (lambda: PL.moon_scene(w=520, h=350, seed=11), 3.1, "ILLUSTRATION · NOT A PHOTOGRAPH"),
}


CTA_POSES = ("jump", "present", "point", "walk", "talk")


def cta_cycle(day: int = 0):
    """The sign-off pose rotates. Same shape as the hook rotation in hooks.py:
    code owns the variety so a month of posts never collapses into one look."""
    name = CTA_POSES[day % len(CTA_POSES)]
    return {"jump": JUMP, "present": PRESENT, "point": POINT,
            "walk": WALK, "talk": TALK}[name], name


def beat_at(t):
    idx = 0
    for i, b in enumerate(BEATS):
        if t >= b[0]:
            idx = i
    return idx, BEATS[idx]


def render_frame(t, day=0):
    TRACE.clear()
    i, (t0, chapter, poses, line, detail, accent, say, counter, plates) = beat_at(t)
    if poses is None:                       # the CTA beat picks its own pose
        poses, _ = cta_cycle(day)
    end = BEATS[i + 1][0] if i + 1 < len(BEATS) else DURATION
    span = end - t0
    local = (t - t0) / max(span, .001)

    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)

    # masthead + progress
    d.text((M, S(70)), "HEADLINNE", font=font(34, 800), fill=INK)
    d.text((W - M, S(74)), "WED 5 AUG", font=font(26, 600), fill=SOFT, anchor="ra")
    d.rectangle([M, S(126), W - M, S(132)], fill=DEEP)
    d.rectangle([M, S(126), M + int((W - 2 * M) * (t / DURATION)), S(132)], fill=accent)

    # chapter
    ch = f"{i + 1:02d} · {chapter.upper()}"
    d.text((M, S(160)), ch, font=font(24, 700), fill=accent)
    note("chapter", *d.textbbox((M, S(160)), ch, font=font(24, 700)))

    # plates - scattered, sliding in
    if plates:
        n = len(plates)
        gutter = S(20)
        for j, key in enumerate(plates):
            mk, ang, cap = PLATE_SPECS[key]
            pl = get_plate(key, mk, ang, cap, 520 if n == 1 else 430)
            ease = min(1.0, local / .28)
            ease = 1 - (1 - ease) ** 3
            left, right = M - gutter, W - M + gutter
            if n == 1:
                px = (W - pl.width) // 2
                py = S(214) + int((1 - ease) * S(40))
            else:
                span = max(0, (right - left) - pl.width)
                px = left + (j * span) // (n - 1)
                py = S(206) + (j % 2) * S(46) + int((1 - ease) * S(40))
            px = max(left, min(px, right - pl.width))     # never leave the frame
            ph = Image.new("RGBA", pl.size, (0, 0, 0, 0))
            ph.paste(pl, (0, 0), pl)
            ph.putalpha(ph.getchannel("A").point(lambda a: int(a * ease)))
            im.paste(ph, (px, py), ph)
            note(f"plate{j}", px, py, px + pl.width, py + pl.height)
        gy = S(944)
    else:
        gy = S(838)

    # ground + Pip
    d.rectangle([0, gy, W, gy + S(5)], fill=DEEP)
    fi = int((t * 7) % len(poses)) if len(poses) > 2 else int((t * 3) % len(poses))
    sp = sprite(poses[fi], max(1, S(12 if plates else 14)))
    travel = int((t / DURATION) * (W - 2 * M - sp.width))
    im.paste(sp, (M - S(30) + travel, gy - sp.height + S(4)), sp)
    note("pip", M - S(30) + travel, gy - sp.height + S(4),
         M - S(30) + travel + sp.width, gy + S(4))

    if say and local < .74:
        f = font(34, 650)
        tw = d.textlength(say, font=f)
        bw, bh = int(tw) + S(44), S(84)
        pip_x = M - S(30) + travel
        gap = S(14)

        # Sit on whichever side of Pip has room. Once he has walked past the
        # midpoint the right side runs out of frame, so the bubble moves left.
        room_right = (W - M) - (pip_x + sp.width + gap)
        room_left = (pip_x - gap) - M
        on_left = room_right < bw and room_left >= bw
        if on_left:
            bx = pip_x - gap - bw
        else:
            bx = pip_x + sp.width + gap
        bx = max(M, min(bx, W - M - bw))          # never leave the margins
        by = gy - sp.height - S(84)

        d.rectangle([bx, by, bx + bw, by + bh], fill=(255, 253, 248))
        d.rectangle([bx, by, bx + bw, by + bh], outline=INK, width=max(2, S(4)))
        d.text((bx + S(22), by + S(20)), say, font=f, fill=INK)

        # the tail descends toward Pip, so it mirrors with the bubble
        s = S(11)
        b = by + bh
        if on_left:
            tx = bx + bw - S(30) - 3 * s
            pts = [(tx, b), (tx + 3 * s, b), (tx + 3 * s, b + 3 * s),
                   (tx + 2 * s, b + 3 * s), (tx + 2 * s, b + 2 * s),
                   (tx + s, b + 2 * s), (tx + s, b + s), (tx, b + s)]
        else:
            tx = bx + S(26)
            pts = [(tx, b), (tx + 3 * s, b)]
            for k in range(3):
                pts += [(tx + (3 - k) * s, b + (k + 1) * s),
                        (tx + (2 - k) * s, b + (k + 1) * s)]
        d.polygon(pts, fill=(255, 253, 248))
        d.line(pts[1:] + [pts[0]], fill=INK, width=max(2, S(4)), joint="curve")
        d.rectangle([tx + 2, b - 3, tx + 3 * s - 2, b + 2], fill=(255, 253, 248))
        note("bubble", bx, by, bx + bw, b + 3 * s)

    # the line, revealed word by word over the first third of the beat
    y = S(966)
    if counter:
        roll = min(1.0, local / .42)
        val = int(8700 * (1 - (1 - roll) ** 3))
        cf = font(140, 800)
        d.text((M, y), f"{val:,}", font=cf, fill=accent)
        cb = d.textbbox((M, y), f"{val:,}", font=cf)
        note("counter", *cb)
        y = cb[3] + S(16)
    y = rich(d, line, M, y, W - 2 * M, 58, accent,
             reveal=min(1.0, local / .34))

    # secondary detail sits below wherever the line actually ended, never on a
    # fixed y - that is what produced the overlap on the counter beat.
    df = font(30, 450)
    dy = y + S(26)
    dh = d.textbbox((M, dy), detail, font=df)
    if dh[3] > S(1246):                     # never crowd the source strip
        dy = S(1246) - (dh[3] - dh[1])
    d.text((M, dy), detail, font=df, fill=SOFT)
    note("detail", *d.textbbox((M, dy), detail, font=df))

    # persistent source strip
    d.rectangle([M, S(1264), W - M, S(1267)], fill=DEEP)
    for k in range(8):
        bx = M + k * S(20)
        d.rectangle([bx, S(1290), bx + S(11), S(1326)], fill=MINT)
    note("strip", M, S(1290), W - M, S(1326))
    d.text((M + S(190), S(1292)), "8 of 8 agree", font=font(26, 700), fill=INK)
    d.text((M, S(1342)), SOURCES, font=font(22, 500), fill=SOFT)
    note("sources", *d.textbbox((M, S(1342)), SOURCES, font=font(22, 500)))

    d.rectangle([M, S(1400), W - M, S(1403)], fill=DEEP)
    d.text((M, S(1416)), "SAFE ZONE ENDS 1450 · IG UI COVERS BELOW", font=font(20, 600), fill=(196, 184, 168))
    return im


def encode(path="reel_draft.mp4"):
    ff = shutil.which("ffmpeg") or "ffmpeg"
    n = int(DURATION * FPS)
    cmd = [ff, "-y", "-f", "rawvideo", "-vcodec", "rawvideo", "-s", f"{W}x{H}",
           "-pix_fmt", "rgb24", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for k in range(n):
        p.stdin.write(render_frame(k / FPS).tobytes())
        if k % 60 == 0:
            print(f"  {k}/{n}", flush=True)
    p.stdin.close()
    err = p.stderr.read().decode(errors="replace")
    if p.wait() != 0:
        sys.exit("ffmpeg failed:\n" + err[-1500:])
    return path


if __name__ == "__main__":
    for tt, name in ((1.0, "d_01"), (5.6, "d_02"), (8.0, "d_03"),
                     (13.0, "d_04"), (20.6, "d_05"), (23.5, "d_06")):
        render_frame(tt).resize((W * 2, H * 2), Image.LANCZOS).save(f"{name}.png")
    print("stills done, encoding...")
    print("wrote", encode())
